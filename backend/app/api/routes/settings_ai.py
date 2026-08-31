"""Integracao de IA configurada pelo painel.

A chave de API entra por aqui, e nunca sai. Ela e cifrada antes de tocar o
banco e as respostas devolvem apenas a mascara (`AIza••••••3f9K`) — o suficiente
para quem administra reconhecer *qual* chave esta configurada, insuficiente
para usar.

Guarda `admin:write`: chave de provedor e segredo da instalacao inteira, no
mesmo nivel do cadastro de usuarios, e nao do conteudo de campanha.
"""

from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep, client_ip, require
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import encrypt_secret, hash_ip, mask_secret
from app.models import AiIntegration, Operator
from app.schemas import AiIntegrationIn, AiIntegrationOut, AiIntegrationTest
from app.services import ai_service
from app.services.event_service import record_audit

router = APIRouter(prefix="/settings/ai", tags=["settings"])
logger = get_logger(__name__)

AdminDep = Depends(require("admin:write"))


def _saida(integracao: AiIntegration | None) -> AiIntegrationOut:
    if integracao is None:
        return AiIntegrationOut(configured=False)
    return AiIntegrationOut(
        configured=True,
        provider=integracao.provider,
        model=integracao.model,
        is_active=integracao.is_active,
        api_key_masked=integracao.api_key_hint,
        last_checked_at=integracao.last_checked_at,
        last_error=integracao.last_error,
        updated_at=integracao.updated_at,
    )


async def _atual(session: SessionDep) -> AiIntegration | None:
    stmt = select(AiIntegration).where(AiIntegration.tenant_id == settings.tenant_id)
    return (await session.execute(stmt)).scalars().first()


@router.get("", response_model=AiIntegrationOut)
async def get_integration(session: SessionDep, _: Operator = AdminDep) -> AiIntegrationOut:
    """Estado da integracao. Nunca devolve a chave — so a mascara."""
    return _saida(await _atual(session))


@router.put("", response_model=AiIntegrationOut)
async def upsert_integration(
    payload: AiIntegrationIn,
    request: Request,
    session: SessionDep,
    operator: Operator = AdminDep,
) -> AiIntegrationOut:
    """Cria ou atualiza a integracao.

    `api_key` vazia numa integracao ja existente mantem a chave atual: e o que
    permite trocar o modelo ou desativar sem precisar digitar o segredo de
    novo — e sem que a tela precise carregar a chave para devolve-la.
    """
    integracao = await _atual(session)

    if integracao is None:
        if not payload.api_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="informe a chave de API para configurar a integracao",
            )
        integracao = AiIntegration(
            tenant_id=settings.tenant_id,
            provider=payload.provider,
            api_key_encrypted=encrypt_secret(payload.api_key),
            api_key_hint=mask_secret(payload.api_key),
            model=payload.model,
            is_active=payload.is_active,
        )
        session.add(integracao)
        acao = "create"
    else:
        integracao.provider = payload.provider
        integracao.model = payload.model
        integracao.is_active = payload.is_active
        if payload.api_key:
            integracao.api_key_encrypted = encrypt_secret(payload.api_key)
            integracao.api_key_hint = mask_secret(payload.api_key)
            # Chave nova invalida o resultado do teste anterior.
            integracao.last_checked_at = None
            integracao.last_error = None
        acao = "update"

    await record_audit(
        session,
        actor_id=operator.id,
        action=acao,
        resource_type="ai_integration",
        # Nunca a chave, nem a mascara: o registro guarda o que foi decidido,
        # nao o segredo.
        metadata={
            "provider": payload.provider.value,
            "model": payload.model,
            "is_active": payload.is_active,
            "key_changed": bool(payload.api_key),
        },
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(integracao)
    return _saida(integracao)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    request: Request, session: SessionDep, operator: Operator = AdminDep
) -> None:
    """Remove a integracao. O atendimento por IA para na hora."""
    integracao = await _atual(session)
    if integracao is None:
        return

    await session.delete(integracao)
    await record_audit(
        session,
        actor_id=operator.id,
        action="delete",
        resource_type="ai_integration",
        metadata={"provider": integracao.provider.value},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()


@router.post("/test", response_model=AiIntegrationTest)
async def test_integration(
    session: SessionDep, _: Operator = AdminDep
) -> AiIntegrationTest:
    """Faz uma chamada real ao provedor com a chave guardada.

    Existe para quem administra descobrir que a chave esta errada aqui, e nao
    quando um lead ficar sem resposta. O resultado fica na linha, entao a tela
    mostra o ultimo teste sem repetir a chamada a cada carregamento.
    """
    integracao = await _atual(session)
    if integracao is None:
        raise HTTPException(status_code=404, detail="nenhuma integracao configurada")

    system = "Voce responde em portugues do Brasil, em uma frase curta."
    historico = [{"role": "user", "content": "Responda apenas: ok"}]

    integracao.last_checked_at = datetime.now(UTC)
    try:
        texto = await ai_service.gerar(integracao, system, historico)
    except httpx.HTTPStatusError as exc:
        detalhe = f"o provedor respondeu {exc.response.status_code}"
        if exc.response.status_code in (401, 403):
            detalhe += " — chave invalida ou sem permissao para este modelo"
        elif exc.response.status_code == 429:
            detalhe += " — cota esgotada; tente de novo mais tarde"
        elif exc.response.status_code == 404:
            detalhe += " — modelo inexistente para esta chave"
        integracao.last_error = detalhe[:255]
    except Exception as exc:
        integracao.last_error = f"falha na chamada: {type(exc).__name__}"[:255]
    else:
        integracao.last_error = None
        await session.commit()
        return AiIntegrationTest(
            ok=True, detail="conexao funcionando", sample=texto[:200]
        )

    logger.warning(
        "teste de integracao de IA falhou",
        extra={"event": "AI_TEST_FAILED", "reason": integracao.last_error},
    )
    await session.commit()
    return AiIntegrationTest(ok=False, detail=integracao.last_error or "falha")
