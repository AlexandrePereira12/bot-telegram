"""Agregacoes do dashboard (M17).

Atribuicao de campanha usa sempre last_touch_campaign_id — decisao registrada
em planejamento/00-indice.md, divergencia 4.

Metrica financeira (CPL/CPA/ROI) so e calculada quando ha dado de
investimento; sem spend informado o campo vem null em vez de zero, para nao
inventar numero que a plataforma de anuncios nao forneceu.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ConversationStatus, EventType, FunnelState, LeadStatus
from app.models import Campaign, Conversation, Conversion, Event, Lead, TelegramUser


def _tenant(stmt: Select, model: Any) -> Select:
    return stmt.where(model.tenant_id == settings.tenant_id)


async def overview(session: AsyncSession, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)

    users = await session.scalar(
        _tenant(select(func.count(TelegramUser.id)), TelegramUser).where(
            TelegramUser.created_at >= since
        )
    )
    leads = await session.scalar(
        _tenant(select(func.count(Lead.id)), Lead).where(Lead.created_at >= since)
    )
    qualified = await session.scalar(
        _tenant(select(func.count(Lead.id)), Lead).where(
            Lead.created_at >= since,
            Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.IN_SUPPORT, LeadStatus.CONVERTED]),
        )
    )
    conversions = await session.scalar(
        _tenant(select(func.count(Conversion.id)), Conversion).where(
            Conversion.converted_at >= since
        )
    )
    awaiting = await session.scalar(
        _tenant(select(func.count(Conversation.id)), Conversation).where(
            Conversation.status == ConversationStatus.OPEN
        )
    )

    users = users or 0
    leads = leads or 0
    conversions = conversions or 0

    avg_seconds = await session.scalar(
        _tenant(
            select(
                func.avg(
                    func.extract("epoch", Lead.converted_at)
                    - func.extract("epoch", Lead.created_at)
                )
            ),
            Lead,
        ).where(Lead.converted_at.is_not(None), Lead.created_at >= since)
    )

    return {
        "period_days": days,
        "users": users,
        "leads": leads,
        "qualified": qualified or 0,
        "conversions": conversions,
        "conversion_rate": round(conversions / leads, 4) if leads else 0.0,
        "awaiting_support": awaiting or 0,
        "avg_seconds_to_conversion": int(avg_seconds) if avg_seconds else None,
    }


async def funnel(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    """Volume por etapa do funil, contando usuarios que ALCANCARAM a etapa.

    Baseado em eventos, nao no estado atual: quem ja avancou continua contando
    nas etapas anteriores, senao o funil apareceria vazio no topo.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    steps = [
        ("entradas", [EventType.USER_STARTED]),
        ("consentimento", [EventType.CONSENT_ACCEPTED]),
        ("idade_confirmada", [EventType.AGE_CONFIRMED]),
        ("qualificacao", [EventType.QUALIFICATION_COMPLETED]),
        ("interesse", [EventType.INTEREST_SELECTED]),
        ("atendimento", [EventType.HUMAN_SUPPORT_REQUESTED]),
        ("conversao", [EventType.CONVERSION]),
    ]

    result: list[dict[str, Any]] = []
    previous: int | None = None
    for label, types in steps:
        count = await session.scalar(
            _tenant(select(func.count(func.distinct(Event.telegram_user_id))), Event).where(
                Event.event_type.in_(types), Event.created_at >= since
            )
        )
        count = count or 0
        result.append(
            {
                "step": label,
                "count": count,
                "drop_from_previous": (previous - count) if previous is not None else None,
            }
        )
        previous = count
    return result


async def campaigns_performance(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(
            Campaign.id,
            Campaign.name,
            Campaign.source,
            Campaign.platform,
            Campaign.spend,
            Campaign.impressions,
            Campaign.clicks,
            func.count(func.distinct(Lead.id)).label("leads"),
            func.count(func.distinct(Conversion.id)).label("conversions"),
        )
        .select_from(Campaign)
        .outerjoin(
            Lead,
            and_(
                Lead.last_touch_campaign_id == Campaign.id,
                Lead.created_at >= since,
            ),
        )
        .outerjoin(Conversion, Conversion.lead_id == Lead.id)
        .where(Campaign.tenant_id == settings.tenant_id)
        .group_by(Campaign.id)
        .order_by(func.count(func.distinct(Lead.id)).desc())
    )

    rows: list[dict[str, Any]] = []
    for row in (await session.execute(stmt)).all():
        spend = float(row.spend) if row.spend is not None else None
        leads = row.leads or 0
        conversions = row.conversions or 0
        rows.append(
            {
                "campaign_id": row.id,
                "name": row.name,
                "source": row.source,
                "platform": row.platform,
                "spend": spend,
                "impressions": row.impressions,
                "clicks": row.clicks,
                "leads": leads,
                "conversions": conversions,
                "conversion_rate": round(conversions / leads, 4) if leads else 0.0,
                # Sem spend informado a metrica fica null, nunca zero.
                "cpl": round(spend / leads, 2) if spend and leads else None,
                "cpa": round(spend / conversions, 2) if spend and conversions else None,
            }
        )
    return rows


async def ads_performance(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(
            Lead.last_touch_ad_id.label("ad_id"),
            func.count(func.distinct(Lead.id)).label("leads"),
            func.count(func.distinct(Conversion.id)).label("conversions"),
        )
        .select_from(Lead)
        .outerjoin(Conversion, Conversion.lead_id == Lead.id)
        .where(
            Lead.tenant_id == settings.tenant_id,
            Lead.created_at >= since,
            Lead.last_touch_ad_id.is_not(None),
        )
        .group_by(Lead.last_touch_ad_id)
        .order_by(func.count(func.distinct(Conversion.id)).desc())
    )
    return [
        {
            "ad_id": row.ad_id,
            "leads": row.leads or 0,
            "conversions": row.conversions or 0,
            "conversion_rate": round((row.conversions or 0) / row.leads, 4) if row.leads else 0.0,
        }
        for row in (await session.execute(stmt)).all()
    ]


async def timeseries(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    day = func.date(Event.created_at).label("day")
    stmt = (
        select(
            day,
            func.count(
                func.distinct(
                    case((Event.event_type == EventType.USER_STARTED, Event.telegram_user_id))
                )
            ).label("users"),
            func.count(case((Event.event_type == EventType.CONVERSION, Event.id))).label(
                "conversions"
            ),
        )
        .where(Event.tenant_id == settings.tenant_id, Event.created_at >= since)
        .group_by(day)
        .order_by(day)
    )
    return [
        {"day": str(row.day), "users": row.users or 0, "conversions": row.conversions or 0}
        for row in (await session.execute(stmt)).all()
    ]


async def state_distribution(session: AsyncSession) -> dict[str, int]:
    stmt = (
        select(TelegramUser.current_state, func.count(TelegramUser.id))
        .where(TelegramUser.tenant_id == settings.tenant_id)
        .group_by(TelegramUser.current_state)
    )
    counts = {state.value: 0 for state in FunnelState}
    for state, total in (await session.execute(stmt)).all():
        counts[str(state)] = total
    return counts
