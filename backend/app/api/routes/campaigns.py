"""Campanhas, conjuntos, anuncios e tracking tokens."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep, client_ip, require
from app.core.config import settings
from app.core.enums import EntityStatus
from app.core.security import hash_ip
from app.models import Ad, AdSet, Campaign, Operator, TrackingToken
from app.schemas import (
    AdCreate,
    AdOut,
    AdSetCreate,
    AdSetOut,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    TrackingTokenCreate,
    TrackingTokenWithLink,
)
from app.services import tracking_service
from app.services.event_service import record_audit

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

ReadDep = Depends(require("campaigns:read"))
WriteDep = Depends(require("campaigns:write"))


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    session: SessionDep,
    _: Operator = ReadDep,
    status_filter: EntityStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Campaign]:
    stmt = select(Campaign).where(Campaign.tenant_id == settings.tenant_id)
    if status_filter:
        stmt = stmt.where(Campaign.status == status_filter)
    stmt = stmt.order_by(Campaign.id.desc()).limit(min(limit, 500)).offset(offset)
    return list((await session.execute(stmt)).scalars())


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate, request: Request, session: SessionDep, operator: Operator = WriteDep
) -> Campaign:
    campaign = Campaign(tenant_id=settings.tenant_id, **payload.model_dump())
    session.add(campaign)
    await session.flush()
    await record_audit(
        session,
        actor_id=operator.id,
        action="create",
        resource_type="campaign",
        resource_id=campaign.id,
        metadata={"name": campaign.name},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return campaign


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: int, session: SessionDep, _: Operator = ReadDep
) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="campanha nao encontrada")
    return campaign


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    request: Request,
    session: SessionDep,
    operator: Operator = WriteDep,
) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="campanha nao encontrada")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(campaign, field, value)

    await record_audit(
        session,
        actor_id=operator.id,
        action="update",
        resource_type="campaign",
        resource_id=campaign.id,
        metadata={"fields": sorted(changes)},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return campaign


# ------------------------------------------------------------------- ad sets
@router.post("/ad-sets", response_model=AdSetOut, status_code=status.HTTP_201_CREATED)
async def create_ad_set(
    payload: AdSetCreate, session: SessionDep, _: Operator = WriteDep
) -> AdSet:
    campaign = await session.get(Campaign, payload.campaign_id)
    if campaign is None or campaign.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="campanha nao encontrada")
    ad_set = AdSet(tenant_id=settings.tenant_id, **payload.model_dump())
    session.add(ad_set)
    await session.commit()
    return ad_set


@router.get("/{campaign_id}/ad-sets", response_model=list[AdSetOut])
async def list_ad_sets(
    campaign_id: int, session: SessionDep, _: Operator = ReadDep
) -> list[AdSet]:
    stmt = select(AdSet).where(
        AdSet.campaign_id == campaign_id, AdSet.tenant_id == settings.tenant_id
    )
    return list((await session.execute(stmt)).scalars())


@router.post("/ads", response_model=AdOut, status_code=status.HTTP_201_CREATED)
async def create_ad(payload: AdCreate, session: SessionDep, _: Operator = WriteDep) -> Ad:
    ad_set = await session.get(AdSet, payload.ad_set_id)
    if ad_set is None or ad_set.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="conjunto nao encontrado")
    ad = Ad(tenant_id=settings.tenant_id, **payload.model_dump())
    session.add(ad)
    await session.commit()
    return ad


# ------------------------------------------------------------ tracking tokens
@router.post(
    "/{campaign_id}/tokens",
    response_model=TrackingTokenWithLink,
    status_code=status.HTTP_201_CREATED,
)
async def create_tracking_token(
    campaign_id: int,
    payload: TrackingTokenCreate,
    request: Request,
    session: SessionDep,
    operator: Operator = WriteDep,
) -> TrackingTokenWithLink:
    try:
        token = await tracking_service.create_token(
            session,
            campaign_id=campaign_id,
            ad_set_id=payload.ad_set_id,
            ad_id=payload.ad_id,
            source=payload.source,
            label=payload.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="create",
        resource_type="tracking_token",
        resource_id=token.id,
        # O token em si nao vai para a auditoria: e um segredo de campanha.
        metadata={"campaign_id": campaign_id, "source": token.source},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()

    bot_username = request.app.state.bot_username
    out = TrackingTokenWithLink.model_validate(token)
    out.deep_link = (
        tracking_service.deep_link(bot_username, token.token) if bot_username else None
    )
    return out


@router.get("/{campaign_id}/tokens", response_model=list[TrackingTokenWithLink])
async def list_tracking_tokens(
    campaign_id: int, request: Request, session: SessionDep, _: Operator = ReadDep
) -> list[TrackingTokenWithLink]:
    stmt = select(TrackingToken).where(
        TrackingToken.campaign_id == campaign_id,
        TrackingToken.tenant_id == settings.tenant_id,
    )
    bot_username = request.app.state.bot_username
    result: list[TrackingTokenWithLink] = []
    for token in (await session.execute(stmt)).scalars():
        item = TrackingTokenWithLink.model_validate(token)
        item.deep_link = (
            tracking_service.deep_link(bot_username, token.token) if bot_username else None
        )
        result.append(item)
    return result


@router.post("/tokens/{token_id}/revoke", response_model=TrackingTokenWithLink)
async def revoke_tracking_token(
    token_id: int, request: Request, session: SessionDep, operator: Operator = WriteDep
) -> TrackingTokenWithLink:
    try:
        token = await tracking_service.revoke_token(session, token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="revoke",
        resource_type="tracking_token",
        resource_id=token.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return TrackingTokenWithLink.model_validate(token)
