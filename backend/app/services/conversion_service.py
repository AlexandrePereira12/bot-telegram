"""Registro de conversao (M19, CU3)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import EventType, FunnelState, LeadStatus
from app.core.logging import get_logger
from app.models import Conversion, Lead, TelegramUser
from app.services.event_service import record_event
from app.services.funnel_service import FunnelError, transition

logger = get_logger(__name__)


class ConversionError(Exception):
    pass


async def register_conversion(
    session: AsyncSession,
    *,
    lead_id: int,
    external_id: str,
    conversion_type: str = "signup",
    value: float | None = None,
    currency: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[Conversion, bool]:
    """Registra a conversao. Retorna (conversao, criada_agora).

    Dedup pela constraint unica (tenant_id, external_id): reentrega do mesmo
    webhook nao duplica a conversao nem a metrica.
    """
    existing = (
        await session.execute(
            select(Conversion).where(
                Conversion.tenant_id == settings.tenant_id,
                Conversion.external_id == external_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "conversao ja registrada; ignorando reentrega",
            extra={"event": "CONVERSION_DUP"},
        )
        return existing, False

    lead = await session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != settings.tenant_id:
        raise ConversionError("lead inexistente")

    conversion = Conversion(
        tenant_id=settings.tenant_id,
        lead_id=lead.id,
        external_id=external_id,
        conversion_type=conversion_type,
        value=value,
        currency=currency,
        conversion_metadata=metadata or {},
        converted_at=datetime.now(UTC),
    )
    session.add(conversion)

    if lead.converted_at is None:
        lead.converted_at = conversion.converted_at
    lead.status = LeadStatus.CONVERTED

    await record_event(
        session,
        EventType.CONVERSION,
        telegram_user_id=lead.telegram_user_id,
        lead_id=lead.id,
        # Atribuicao autoritativa da conversao: last touch.
        campaign_id=lead.last_touch_campaign_id,
        metadata={
            "conversion_type": conversion_type,
            "value": float(value) if value is not None else None,
            "currency": currency,
        },
    )

    user = await session.get(TelegramUser, lead.telegram_user_id)
    if user is not None:
        try:
            await transition(session, user, FunnelState.CONVERTED, lead=lead)
        except FunnelError as exc:
            # Conversao pode chegar de um lead que abandonou o funil (EXIT) ou
            # ja convertido. O registro financeiro vale; o estado nao regride.
            logger.info(
                "conversao registrada sem mudanca de estado",
                extra={"event": "CONVERSION_STATE_SKIPPED", "reason": str(exc)},
            )

    await session.flush()
    return conversion, True
