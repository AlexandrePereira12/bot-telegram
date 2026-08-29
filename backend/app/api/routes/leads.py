"""Leads, timeline consolidada e ingestao de eventos."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import SessionDep, require
from app.core.config import settings
from app.core.enums import LeadStatus
from app.models import Conversation, Conversion, Event, Lead, Message, Operator, TelegramUser
from app.schemas import EventCreate, EventOut, LeadDetail, LeadOut, TimelineEntry
from app.services.event_service import record_event
from app.services.idempotency_service import claim

router = APIRouter(tags=["leads"])

LeadsRead = Depends(require("leads:read"))
EventsWrite = Depends(require("events:write"))


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(
    session: SessionDep,
    _: Operator = LeadsRead,
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    campaign_id: int | None = None,
    source: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Lead]:
    stmt = select(Lead).where(Lead.tenant_id == settings.tenant_id)
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    if campaign_id:
        # Filtro por campanha usa last touch, a atribuicao autoritativa.
        stmt = stmt.where(Lead.last_touch_campaign_id == campaign_id)
    if source:
        stmt = stmt.where(Lead.source == source)
    if created_from:
        stmt = stmt.where(Lead.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Lead.created_at <= created_to)
    stmt = stmt.order_by(Lead.id.desc()).limit(min(limit, 500)).offset(offset)
    return list((await session.execute(stmt)).scalars())


@router.get("/leads/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: int, session: SessionDep, _: Operator = LeadsRead) -> LeadDetail:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="lead nao encontrado")
    user = await session.get(TelegramUser, lead.telegram_user_id)

    detail = LeadDetail.model_validate(lead)
    if user is not None:
        detail.telegram_username = user.username
        detail.telegram_first_name = user.first_name
        detail.current_state = user.current_state
        detail.consent_status = user.consent_status.value
        detail.age_confirmed = user.age_confirmed
    return detail


@router.get("/leads/{lead_id}/history", response_model=list[TimelineEntry])
async def lead_history(
    lead_id: int, session: SessionDep, _: Operator = LeadsRead
) -> list[TimelineEntry]:
    """Timeline consolidada do lead: eventos + mensagens + conversoes (M15)."""
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="lead nao encontrado")

    entries: list[TimelineEntry] = []

    events = (
        await session.execute(
            select(Event).where(Event.lead_id == lead.id, Event.tenant_id == settings.tenant_id)
        )
    ).scalars()
    for event in events:
        entries.append(
            TimelineEntry(
                kind="event",
                at=event.created_at,
                label=event.event_type.value,
                detail=event.event_metadata,
            )
        )

    messages = (
        await session.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.telegram_user_id == lead.telegram_user_id,
                Message.tenant_id == settings.tenant_id,
            )
        )
    ).scalars()
    for message in messages:
        entries.append(
            TimelineEntry(
                kind="message",
                at=message.created_at,
                label=f"{message.direction.value}:{message.sender_type.value}",
                detail={"content": message.content, "sender_id": message.sender_id},
            )
        )

    conversions = (
        await session.execute(
            select(Conversion).where(
                Conversion.lead_id == lead.id, Conversion.tenant_id == settings.tenant_id
            )
        )
    ).scalars()
    for conversion in conversions:
        entries.append(
            TimelineEntry(
                kind="conversion",
                at=conversion.converted_at,
                label=conversion.conversion_type,
                detail={
                    "value": float(conversion.value) if conversion.value is not None else None,
                    "currency": conversion.currency,
                    "external_id": conversion.external_id,
                },
            )
        )

    entries.sort(key=lambda e: e.at)
    return entries


@router.get("/events", response_model=list[EventOut])
async def list_events(
    session: SessionDep,
    _: Operator = LeadsRead,
    lead_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Event]:
    stmt = select(Event).where(Event.tenant_id == settings.tenant_id)
    if lead_id:
        stmt = stmt.where(Event.lead_id == lead_id)
    stmt = stmt.order_by(Event.id.desc()).limit(min(limit, 500)).offset(offset)
    return list((await session.execute(stmt)).scalars())


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate, session: SessionDep, _: Operator = EventsWrite
) -> Event:
    """Ingestao manual de evento.

    Idempotencia verificada antes de qualquer efeito colateral: chave repetida
    devolve o evento ja gravado em vez de criar outro.
    """
    is_new = await claim(session, "events", payload.idempotency_key)
    if not is_new:
        existing = (
            await session.execute(
                select(Event)
                .where(
                    Event.tenant_id == settings.tenant_id,
                    Event.event_type == payload.event_type,
                    Event.lead_id == payload.lead_id,
                )
                .order_by(Event.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        raise HTTPException(status_code=409, detail="chave de idempotencia ja utilizada")

    event = await record_event(
        session,
        payload.event_type,
        telegram_user_id=payload.telegram_user_id,
        lead_id=payload.lead_id,
        campaign_id=payload.campaign_id,
        metadata=payload.metadata,
    )
    await session.commit()
    await session.refresh(event)
    return event
