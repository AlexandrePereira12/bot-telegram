"""Usuario do Telegram e lead: criacao, atribuicao first/last touch (M6, M11)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import LeadStatus
from app.core.logging import get_logger
from app.models import Lead, TelegramUser
from app.services.tracking_service import Attribution

logger = get_logger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language: str | None = None,
) -> tuple[TelegramUser, bool]:
    """Retorna (usuario, criado_agora)."""
    stmt = select(TelegramUser).where(
        TelegramUser.telegram_id == telegram_id,
        TelegramUser.tenant_id == settings.tenant_id,
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is not None:
        # Perfil pode mudar no Telegram; estado do funil nunca e resetado aqui.
        user.username = username or user.username
        user.first_name = first_name or user.first_name
        user.language = language or user.language
        return user, False

    user = TelegramUser(
        tenant_id=settings.tenant_id,
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        language=language,
    )
    session.add(user)
    await session.flush()
    return user, True


async def get_or_create_lead(
    session: AsyncSession, user: TelegramUser, attribution: Attribution
) -> tuple[Lead, bool]:
    """Cria o lead ou atualiza sua atribuicao.

    first_touch e gravado uma unica vez e nunca muda. last_touch e
    reescrito a cada nova entrada atribuida e e a fonte autoritativa das
    metricas de conversao/CPA (planejamento/arquitetura.md).
    """
    stmt = select(Lead).where(
        Lead.telegram_user_id == user.id,
        Lead.tenant_id == settings.tenant_id,
    )
    lead = (await session.execute(stmt)).scalar_one_or_none()
    now = datetime.now(UTC)

    if lead is None:
        lead = Lead(
            tenant_id=settings.tenant_id,
            telegram_user_id=user.id,
            first_touch_campaign_id=attribution.campaign_id,
            first_touch_ad_set_id=attribution.ad_set_id,
            first_touch_ad_id=attribution.ad_id,
            first_touch_source=attribution.source,
            last_touch_campaign_id=attribution.campaign_id,
            last_touch_ad_set_id=attribution.ad_set_id,
            last_touch_ad_id=attribution.ad_id,
            last_touch_source=attribution.source,
            source=attribution.source,
            status=LeadStatus.NEW,
            last_interaction_at=now,
        )
        session.add(lead)
        await session.flush()
        return lead, True

    lead.last_interaction_at = now
    # Reentrada organica nao sobrescreve uma atribuicao paga anterior: sem
    # campanha nova nao ha novo "touch" a registrar.
    if attribution.is_attributed:
        lead.last_touch_campaign_id = attribution.campaign_id
        lead.last_touch_ad_set_id = attribution.ad_set_id
        lead.last_touch_ad_id = attribution.ad_id
        lead.last_touch_source = attribution.source
        lead.source = attribution.source
        if lead.first_touch_campaign_id is None:
            lead.first_touch_campaign_id = attribution.campaign_id
            lead.first_touch_ad_set_id = attribution.ad_set_id
            lead.first_touch_ad_id = attribution.ad_id
            lead.first_touch_source = attribution.source
    return lead, False


async def get_lead_by_user(session: AsyncSession, telegram_user_id: int) -> Lead | None:
    stmt = select(Lead).where(
        Lead.telegram_user_id == telegram_user_id,
        Lead.tenant_id == settings.tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()
