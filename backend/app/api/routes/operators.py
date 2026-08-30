"""Cadastro e consulta de operadores do dashboard.

Existe em paralelo ao `python -m app.cli create-admin` e nao o substitui:
esta rota exige um ADMIN ja autenticado, entao o primeiro administrador de
uma instalacao continua vindo da CLI. Depois dele, o cadastro dos demais
deixa de precisar de acesso ao servidor.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, client_ip, require
from app.core.config import settings
from app.core.enums import OperatorRole
from app.core.security import hash_ip
from app.models import AuditLog, Conversation, Message, Operator
from app.schemas import OperatorAdminOut, OperatorCreate, OperatorCreated, OperatorUpdate
from app.services.auth_service import (
    ROLES_REQUIRING_2FA,
    AuthError,
    create_operator,
    ensure_admin_remains,
    reset_totp,
)
from app.services.event_service import record_audit

router = APIRouter(prefix="/operators", tags=["operators"])

AdminDep = Depends(require("admin:write"))


@router.get("", response_model=list[OperatorAdminOut])
async def list_operators(
    session: SessionDep,
    _: Operator = AdminDep,
    limit: int = 200,
    offset: int = 0,
) -> list[Operator]:
    stmt = (
        select(Operator)
        .where(Operator.tenant_id == settings.tenant_id)
        .order_by(Operator.id.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars())


@router.post("", response_model=OperatorCreated, status_code=status.HTTP_201_CREATED)
async def create_operator_route(
    payload: OperatorCreate,
    request: Request,
    session: SessionDep,
    operator: Operator = AdminDep,
) -> OperatorCreated:
    """Cria um operador com o perfil informado.

    Perfil que exige 2FA (hoje ADMIN) nao ganha segredo aqui: ele e gerado
    no primeiro login do proprio dono, pelo fluxo de QR — o mesmo motivo
    pelo qual a CLI tambem nao o gera.
    """
    generated = payload.password is None
    password = payload.password or secrets.token_urlsafe(16)

    try:
        novo = await create_operator(
            session,
            email=payload.email,
            password=password,
            role=payload.role,
            full_name=payload.full_name,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="ja existe operador com esse e-mail"
        ) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="create",
        resource_type="operator",
        resource_id=novo.id,
        # Sem senha e sem hash: a auditoria registra quem criou quem, com que
        # perfil — nunca o segredo.
        metadata={"email": novo.email, "role": novo.role.value},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(novo)

    return OperatorCreated(
        **OperatorAdminOut.model_validate(novo).model_dump(),
        generated_password=password if generated else None,
    )


async def _buscar(session: AsyncSession, operator_id: int) -> Operator:
    """Operador do proprio tenant. Linha de outra instalacao responde 404,
    nunca 403: a existencia da conta alheia nao e informacao a dar."""
    alvo = await session.get(Operator, operator_id)
    if alvo is None or alvo.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operador nao encontrado")
    return alvo


def _recusa_acao_em_si_mesmo(ator: Operator, alvo: Operator) -> None:
    """Perfil, acesso e exclusao da propria conta ficam fora do painel.

    Um administrador que se rebaixa ou se desativa perde o acesso na mesma
    requisicao — e, se for o unico, tranca a instalacao inteira. Editar o
    proprio nome continua liberado.
    """
    if ator.id == alvo.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="voce nao pode alterar o proprio perfil, acesso ou cadastro por aqui",
        )


async def _tem_historico(session: AsyncSession, operator_id: int) -> bool:
    """Diz se o operador ja deixou rastro que a exclusao apagaria.

    Todas as chaves estrangeiras para `operators` sao ON DELETE SET NULL: um
    delete passaria sem erro e, em silencio, tiraria o autor de linhas da
    auditoria (que e append-only) e o remetente de mensagens ja enviadas.
    """
    auditoria = await session.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.actor_id == operator_id)
    )
    mensagens = await session.scalar(
        select(func.count(Message.id)).where(Message.sender_id == operator_id)
    )
    conversas = await session.scalar(
        select(func.count(Conversation.id)).where(
            or_(
                Conversation.assigned_to == operator_id,
                Conversation.closed_by_operator_id == operator_id,
            )
        )
    )
    return bool((auditoria or 0) + (mensagens or 0) + (conversas or 0))


@router.patch("/{operator_id}", response_model=OperatorAdminOut)
async def update_operator(
    operator_id: int,
    payload: OperatorUpdate,
    request: Request,
    session: SessionDep,
    operator: Operator = AdminDep,
) -> Operator:
    """Altera nome, perfil ou acesso de um operador."""
    alvo = await _buscar(session, operator_id)
    mudancas = payload.model_dump(exclude_unset=True)

    if "role" in mudancas or "is_active" in mudancas:
        _recusa_acao_em_si_mesmo(operator, alvo)

    novo_role = mudancas.get("role", alvo.role)
    novo_ativo = mudancas.get("is_active", alvo.is_active)
    # Deixaria de ser um ADMIN ativo? Entao precisa sobrar outro.
    if alvo.role == OperatorRole.ADMIN and alvo.is_active:
        if novo_role != OperatorRole.ADMIN or not novo_ativo:
            try:
                await ensure_admin_remains(session, excluding=alvo.id)
            except AuthError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(exc)
                ) from exc

    for campo, valor in mudancas.items():
        setattr(alvo, campo, valor)

    await record_audit(
        session,
        actor_id=operator.id,
        action="update",
        resource_type="operator",
        resource_id=alvo.id,
        metadata={"email": alvo.email, **{k: str(v) for k, v in mudancas.items()}},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(alvo)
    return alvo


@router.post("/{operator_id}/reset-2fa", response_model=OperatorAdminOut)
async def reset_2fa(
    operator_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = AdminDep,
) -> Operator:
    """Descarta o autenticador do operador (celular perdido ou trocado).

    Mesmo efeito do `python -m app.cli reset-2fa`: o segredo antigo e jogado
    fora e o proximo login mostra um QR novo. Nada e reexibido aqui.
    """
    alvo = await _buscar(session, operator_id)
    _recusa_acao_em_si_mesmo(operator, alvo)

    if alvo.role not in ROLES_REQUIRING_2FA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="este perfil nao usa autenticador",
        )

    reset_totp(alvo)
    await record_audit(
        session,
        actor_id=operator.id,
        action="reset_2fa",
        resource_type="operator",
        resource_id=alvo.id,
        metadata={"email": alvo.email},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(alvo)
    return alvo


@router.delete("/{operator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operator(
    operator_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = AdminDep,
) -> None:
    """Exclui em definitivo — so enquanto o operador nao produziu historico.

    Quem ja atendeu, respondeu ou gerou linha de auditoria nao e apagado: a
    saida correta e desativar (`is_active=false`), que corta o acesso na
    mesma hora e preserva o rastro de quem fez o que.
    """
    alvo = await _buscar(session, operator_id)
    _recusa_acao_em_si_mesmo(operator, alvo)

    if alvo.role == OperatorRole.ADMIN and alvo.is_active:
        try:
            await ensure_admin_remains(session, excluding=alvo.id)
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if await _tem_historico(session, alvo.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "este usuario ja tem historico no sistema e nao pode ser excluido "
                "sem apagar o rastro de auditoria; desative o acesso"
            ),
        )

    email = alvo.email
    await session.delete(alvo)
    await record_audit(
        session,
        actor_id=operator.id,
        action="delete",
        resource_type="operator",
        resource_id=operator_id,
        metadata={"email": email},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
