"""Tracking token e atribuicao first/last touch."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Campaign
from app.services import lead_service, tracking_service


async def test_token_invalido_cai_em_organic(session: AsyncSession):
    attribution = await tracking_service.resolve_token(session, "t_naoexiste")
    assert attribution.source == "organic"
    assert attribution.is_attributed is False


async def test_token_ausente_cai_em_organic(session: AsyncSession):
    assert (await tracking_service.resolve_token(session, None)).source == "organic"
    assert (await tracking_service.resolve_token(session, "")).source == "organic"


async def test_token_valido_resolve_campanha(session: AsyncSession, campaign: Campaign):
    token = await tracking_service.create_token(session, campaign_id=campaign.id, source="meta")
    attribution = await tracking_service.resolve_token(session, token.token)
    assert attribution.campaign_id == campaign.id
    assert attribution.source == "meta"


async def test_token_revogado_cai_em_organic(session: AsyncSession, campaign: Campaign):
    token = await tracking_service.create_token(session, campaign_id=campaign.id)
    await tracking_service.revoke_token(session, token.id)
    await session.flush()

    attribution = await tracking_service.resolve_token(session, token.token)
    assert attribution.source == "organic"
    assert attribution.campaign_id is None


async def test_first_touch_preservado_last_touch_atualizado(
    session: AsyncSession, campaign: Campaign
):
    """Segunda entrada por campanha diferente atualiza so o last touch."""
    outra = Campaign(
        tenant_id=settings.tenant_id, name="Segunda", source="google", external_id="test-002"
    )
    session.add(outra)
    await session.flush()

    token_a = await tracking_service.create_token(session, campaign_id=campaign.id, source="meta")
    token_b = await tracking_service.create_token(session, campaign_id=outra.id, source="google")

    user, _ = await lead_service.get_or_create_user(session, telegram_id=2001)
    lead, created = await lead_service.get_or_create_lead(
        session, user, await tracking_service.resolve_token(session, token_a.token)
    )
    assert created is True
    assert lead.first_touch_campaign_id == campaign.id
    assert lead.last_touch_campaign_id == campaign.id

    lead, created = await lead_service.get_or_create_lead(
        session, user, await tracking_service.resolve_token(session, token_b.token)
    )
    assert created is False
    assert lead.first_touch_campaign_id == campaign.id, "first touch nunca muda"
    assert lead.last_touch_campaign_id == outra.id, "last touch acompanha a ultima origem"


async def test_reentrada_organica_nao_apaga_atribuicao_paga(
    session: AsyncSession, campaign: Campaign
):
    token = await tracking_service.create_token(session, campaign_id=campaign.id, source="meta")
    user, _ = await lead_service.get_or_create_user(session, telegram_id=2002)
    await lead_service.get_or_create_lead(
        session, user, await tracking_service.resolve_token(session, token.token)
    )

    lead, _ = await lead_service.get_or_create_lead(session, user, tracking_service.ORGANIC)
    assert lead.last_touch_campaign_id == campaign.id
