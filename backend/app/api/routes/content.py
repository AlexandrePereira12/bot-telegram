"""Conteudo do funil: textos, opcoes de qualificacao e midia.

Tudo aqui e por campanha, com `campaign_id=None` representando o padrao
global. Etapas de efeito legal (consentimento e age gate) so aceitam edicao
global — ver GLOBAL_ONLY_STEPS.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import SessionDep, client_ip, require
from app.core.config import settings
from app.core.enums import GLOBAL_ONLY_STEPS, FunnelStep
from app.core.logging import get_logger
from app.core.security import hash_ip
from app.models import Campaign, FunnelContent, Operator, QualificationOption
from app.schemas import (
    FunnelContentIn,
    FunnelContentOut,
    MediaUploadOut,
    QualificationOptionIn,
    QualificationOptionOut,
    ResolvedStepOut,
)
from app.services import content_service, media_service
from app.services.event_service import record_audit

router = APIRouter(prefix="/content", tags=["content"])
logger = get_logger(__name__)

ContentRead = Depends(require("campaigns:read"))
ContentWrite = Depends(require("campaigns:write"))


async def _ensure_campaign(session: SessionDep, campaign_id: int | None) -> None:
    if campaign_id is None:
        return
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="campanha nao encontrada")


def _assert_step_allowed(step: FunnelStep, campaign_id: int | None) -> None:
    if campaign_id is not None and step in GLOBAL_ONLY_STEPS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"a etapa {step.value} so pode ser editada globalmente. "
                "O aceite e auditado por versao dos termos: se o texto variasse "
                "por campanha, o registro deixaria de provar o que foi aceito."
            ),
        )


# ------------------------------------------------------------------- leitura
@router.get("/steps", response_model=list[ResolvedStepOut])
async def list_steps(
    session: SessionDep,
    _: Operator = ContentRead,
    campaign_id: int | None = None,
) -> list[ResolvedStepOut]:
    """Como cada etapa fica para a campanha, indicando a origem do texto."""
    await _ensure_campaign(session, campaign_id)

    stmt = select(FunnelContent).where(FunnelContent.tenant_id == settings.tenant_id)
    rows = list((await session.execute(stmt)).scalars())
    por_campanha = {r.step: r for r in rows if r.campaign_id == campaign_id}
    globais = {r.step: r for r in rows if r.campaign_id is None}

    resultado: list[ResolvedStepOut] = []
    for step in FunnelStep:
        editable = step not in GLOBAL_ONLY_STEPS
        row = por_campanha.get(step) if (campaign_id and editable) else None
        origin = "campanha"
        if row is None:
            row = globais.get(step)
            origin = "global"
        if row is None:
            resultado.append(
                ResolvedStepOut(
                    step=step,
                    body=content_service._fallback(step),
                    origin="codigo",
                    editable_per_campaign=editable,
                )
            )
            continue
        resultado.append(
            ResolvedStepOut(
                step=step,
                body=row.body,
                media_id=row.media_id,
                media_type=row.media_type,
                origin=origin,
                editable_per_campaign=editable,
            )
        )
    return resultado


# -------------------------------------------------------------------- escrita
@router.put("/steps", response_model=FunnelContentOut)
async def upsert_step(
    payload: FunnelContentIn,
    request: Request,
    session: SessionDep,
    operator: Operator = ContentWrite,
    campaign_id: int | None = None,
) -> FunnelContent:
    """Cria ou atualiza o texto de uma etapa.

    O corpo passa pela validacao de compliance no schema: promessa de ganho
    e recusada com 422 antes de chegar aqui.
    """
    await _ensure_campaign(session, campaign_id)
    _assert_step_allowed(payload.step, campaign_id)

    stmt = select(FunnelContent).where(
        FunnelContent.tenant_id == settings.tenant_id,
        FunnelContent.step == payload.step,
        FunnelContent.campaign_id.is_(None)
        if campaign_id is None
        else FunnelContent.campaign_id == campaign_id,
    )
    content = (await session.execute(stmt)).scalar_one_or_none()

    if content is None:
        content = FunnelContent(
            tenant_id=settings.tenant_id, campaign_id=campaign_id, step=payload.step
        )
        session.add(content)

    anterior = content.media_id
    content.body = payload.body
    content.media_id = payload.media_id
    content.media_type = payload.media_type

    # Midia trocada: apaga a antiga para o banco nao crescer com orfaos a cada
    # edicao.
    if anterior and anterior != payload.media_id:
        await media_service.delete(session, anterior)

    await record_audit(
        session,
        actor_id=operator.id,
        action="update",
        resource_type="funnel_content",
        resource_id=f"{campaign_id or 'global'}:{payload.step.value}",
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(content)
    return content


@router.delete("/steps/{step}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(
    step: FunnelStep,
    request: Request,
    session: SessionDep,
    operator: Operator = ContentWrite,
    campaign_id: int | None = None,
) -> None:
    """Remove o texto proprio da campanha; ela volta a usar o global."""
    if campaign_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="o texto global nao pode ser removido, apenas editado",
        )

    stmt = select(FunnelContent).where(
        FunnelContent.tenant_id == settings.tenant_id,
        FunnelContent.campaign_id == campaign_id,
        FunnelContent.step == step,
    )
    content = (await session.execute(stmt)).scalar_one_or_none()
    if content is None:
        return

    if content.media_id:
        await media_service.delete(session, content.media_id)
    await session.delete(content)
    await record_audit(
        session,
        actor_id=operator.id,
        action="delete",
        resource_type="funnel_content",
        resource_id=f"{campaign_id}:{step.value}",
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()


# ----------------------------------------------------- opcoes de qualificacao
@router.get("/options", response_model=list[QualificationOptionOut])
async def list_options(
    session: SessionDep,
    _: Operator = ContentRead,
    campaign_id: int | None = None,
) -> list[QualificationOption]:
    await _ensure_campaign(session, campaign_id)
    stmt = (
        select(QualificationOption)
        .where(
            QualificationOption.tenant_id == settings.tenant_id,
            QualificationOption.campaign_id.is_(None)
            if campaign_id is None
            else QualificationOption.campaign_id == campaign_id,
        )
        .order_by(QualificationOption.sort_order, QualificationOption.id)
    )
    return list((await session.execute(stmt)).scalars())


@router.put("/options", response_model=QualificationOptionOut)
async def upsert_option(
    payload: QualificationOptionIn,
    request: Request,
    session: SessionDep,
    operator: Operator = ContentWrite,
    campaign_id: int | None = None,
) -> QualificationOption:
    await _ensure_campaign(session, campaign_id)

    stmt = select(QualificationOption).where(
        QualificationOption.tenant_id == settings.tenant_id,
        QualificationOption.key == payload.key,
        QualificationOption.campaign_id.is_(None)
        if campaign_id is None
        else QualificationOption.campaign_id == campaign_id,
    )
    option = (await session.execute(stmt)).scalar_one_or_none()

    if option is None:
        option = QualificationOption(
            tenant_id=settings.tenant_id, campaign_id=campaign_id, key=payload.key
        )
        session.add(option)

    anterior = option.response_media_id
    option.label = payload.label
    option.target = payload.target
    option.sort_order = payload.sort_order
    option.is_active = payload.is_active
    option.response_body = payload.response_body
    option.response_media_id = payload.response_media_id
    option.response_media_type = payload.response_media_type

    # Midia trocada: apaga a antiga para o banco nao acumular orfaos.
    if anterior and anterior != payload.response_media_id:
        await media_service.delete(session, anterior)

    await record_audit(
        session,
        actor_id=operator.id,
        action="update",
        resource_type="qualification_option",
        resource_id=f"{campaign_id or 'global'}:{payload.key}",
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(option)
    return option


@router.delete("/options/{option_id}", response_model=QualificationOptionOut)
async def deactivate_option(
    option_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = ContentWrite,
) -> QualificationOption:
    """Desativa a opcao.

    Nao apaga de proposito: `leads.interest` e os eventos ja gravados
    referenciam a chave, e remove-la deixaria buraco no historico e no
    analytics. Desativada, ela some do teclado e continua resolvendo o passado.
    """
    option = await session.get(QualificationOption, option_id)
    if option is None or option.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="opcao nao encontrada")

    option.is_active = False
    await record_audit(
        session,
        actor_id=operator.id,
        action="deactivate",
        resource_type="qualification_option",
        resource_id=option.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(option)
    return option


# ----------------------------------------------------------------------- midia
@router.post("/media", response_model=MediaUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    request: Request,
    session: SessionDep,
    file: UploadFile = File(...),
    operator: Operator = ContentWrite,
) -> MediaUploadOut:
    """Recebe imagem, video ou audio para usar nas mensagens do funil.

    Tipo detectado pelo conteudo do arquivo, nao pela extensao enviada.
    """
    content = await file.read()
    try:
        media = await media_service.save(session, content)
    except media_service.MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="upload",
        resource_type="media",
        resource_id=media.id,
        metadata={"type": media.media_type.value, "bytes": media.size_bytes},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return MediaUploadOut(
        media_id=media.id, media_type=media.media_type, size_bytes=media.size_bytes
    )
