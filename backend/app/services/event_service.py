"""Registro de eventos do funil e log de auditoria."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import EventType
from app.core.logging import get_logger
from app.models import AuditLog, Event

logger = get_logger(__name__)


async def record_event(
    session: AsyncSession,
    event_type: EventType,
    *,
    telegram_user_id: int | None = None,
    lead_id: int | None = None,
    campaign_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Event:
    """Grava um evento do funil. Nao commita — quem orquestra decide a transacao."""
    event = Event(
        tenant_id=settings.tenant_id,
        telegram_user_id=telegram_user_id,
        lead_id=lead_id,
        campaign_id=campaign_id,
        event_type=event_type,
        event_metadata=metadata or {},
    )
    session.add(event)
    logger.info(
        "evento registrado",
        extra={"event": event_type.value, "lead_id": lead_id, "user_id": telegram_user_id},
    )
    return event


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    resource_type: str,
    # int aceito porque quase toda chamada passa o id da linha; a conversao
    # para texto acontece aqui, num lugar so.
    resource_id: str | int | None = None,
    result: str = "success",
    metadata: dict[str, Any] | None = None,
    ip_hash: str | None = None,
) -> AuditLog:
    """Auditoria de acao administrativa.

    metadata nunca deve conter senha, token ou segredo — quem chama e
    responsavel por nao passar esses campos.
    """
    entry = AuditLog(
        tenant_id=settings.tenant_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        result=result,
        audit_metadata=metadata or {},
        ip_hash=ip_hash,
    )
    session.add(entry)
    return entry
