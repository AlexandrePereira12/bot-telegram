"""Conversas e atendimento humano (M13, M14, CU2)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    ConversationOutcome,
    ConversationStatus,
    EventType,
    FunnelState,
    LeadStatus,
    MediaType,
    MessageDirection,
    SenderType,
)
from app.core.logging import get_logger
from app.models import Conversation, Message, Operator, TelegramUser
from app.services.conversion_service import register_conversion
from app.services.event_service import record_event
from app.services.funnel_service import FunnelError, transition
from app.services.lead_service import get_lead_by_user

logger = get_logger(__name__)


class ConversationError(Exception):
    pass


async def get_or_create_conversation(
    session: AsyncSession, telegram_user_id: int
) -> Conversation:
    stmt = (
        select(Conversation)
        .where(
            Conversation.telegram_user_id == telegram_user_id,
            Conversation.tenant_id == settings.tenant_id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.id.desc())
        .limit(1)
    )
    conversation = (await session.execute(stmt)).scalar_one_or_none()
    if conversation is not None:
        return conversation

    conversation = Conversation(
        tenant_id=settings.tenant_id,
        telegram_user_id=telegram_user_id,
        status=ConversationStatus.OPEN,
        started_at=datetime.now(UTC),
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def record_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    direction: MessageDirection,
    sender_type: SenderType,
    content: str | None,
    sender_id: int | None = None,
    telegram_message_id: int | None = None,
    message_type: str = "text",
    media_path: str | None = None,
    media_type: MediaType | None = None,
) -> Message:
    message = Message(
        tenant_id=settings.tenant_id,
        conversation_id=conversation.id,
        telegram_message_id=telegram_message_id,
        direction=direction,
        sender_type=sender_type,
        sender_id=sender_id,
        message_type=message_type,
        content=content,
        media_path=media_path,
        media_type=media_type,
    )
    session.add(message)
    await record_event(
        session,
        EventType.MESSAGE_RECEIVED
        if direction == MessageDirection.INBOUND
        else EventType.MESSAGE_SENT,
        telegram_user_id=conversation.telegram_user_id,
        metadata={"sender_type": sender_type.value, "message_type": message_type},
    )
    return message


async def is_under_human_support(session: AsyncSession, telegram_user_id: int) -> bool:
    """Enquanto ha operador atribuido, a automacao nao responde (M14)."""
    stmt = select(Conversation.assigned_to).where(
        Conversation.telegram_user_id == telegram_user_id,
        Conversation.tenant_id == settings.tenant_id,
        Conversation.status == ConversationStatus.ASSIGNED,
        Conversation.assigned_to.is_not(None),
    )
    return (await session.execute(stmt)).first() is not None


async def assign(
    session: AsyncSession, conversation_id: int, operator: Operator
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise ConversationError("conversa inexistente")
    if conversation.status == ConversationStatus.CLOSED:
        raise ConversationError("conversa encerrada")
    if conversation.assigned_to is not None and conversation.assigned_to != operator.id:
        raise ConversationError("conversa ja atribuida a outro operador")

    conversation.assigned_to = operator.id
    conversation.assigned_at = datetime.now(UTC)
    conversation.status = ConversationStatus.ASSIGNED

    user = await session.get(TelegramUser, conversation.telegram_user_id)
    lead = await get_lead_by_user(session, conversation.telegram_user_id) if user else None
    if user is not None:
        try:
            await transition(session, user, FunnelState.HUMAN_SUPPORT, lead=lead)
        except FunnelError:
            # Assumir a conversa e sempre permitido; o estado do funil so muda
            # quando a transicao for valida a partir do estado atual.
            pass

    await record_event(
        session,
        EventType.HUMAN_SUPPORT_ASSIGNED,
        telegram_user_id=conversation.telegram_user_id,
        lead_id=lead.id if lead else None,
        metadata={"operator_id": operator.id},
    )
    return conversation


async def release(
    session: AsyncSession, conversation_id: int, operator: Operator
) -> Conversation:
    """Devolve a conversa para a automacao, sem encerrar.

    Acao diferente de encerrar: aqui o atendimento continua em aberto, so sai
    das maos deste operador — por isso nao pede desfecho.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise ConversationError("conversa inexistente")

    conversation.assigned_to = None
    conversation.assigned_at = None
    conversation.status = ConversationStatus.OPEN

    await record_event(
        session,
        EventType.HUMAN_SUPPORT_RELEASED,
        telegram_user_id=conversation.telegram_user_id,
        metadata={"operator_id": operator.id},
    )
    return conversation


async def close_with_outcome(
    session: AsyncSession,
    conversation_id: int,
    operator: Operator,
    *,
    outcome: ConversationOutcome,
    reason: str | None = None,
    value: float | None = None,
    currency: str | None = None,
) -> Conversation:
    """Encerra o atendimento registrando o desfecho.

    Convertido passa por `register_conversion`, para que o evento CONVERSION,
    o `converted_at` e a atribuicao por last touch aconteçam num lugar so. O
    `external_id` e deterministico (`manual:<id da conversa>`), entao clicar
    duas vezes em encerrar cai na constraint unica de conversoes e nao
    duplica a metrica.

    Depois de encerrada, uma mensagem nova do lead abre outro ciclo — ver
    `funnel_service.reopen`.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise ConversationError("conversa inexistente")
    if conversation.status == ConversationStatus.CLOSED:
        raise ConversationError("atendimento ja encerrado")

    lead = await get_lead_by_user(session, conversation.telegram_user_id)

    if outcome == ConversationOutcome.CONVERTED:
        if lead is None:
            raise ConversationError("lead nao encontrado para registrar a conversao")
        await register_conversion(
            session,
            lead_id=lead.id,
            external_id=f"manual:{conversation.id}",
            conversion_type="atendimento",
            value=value,
            currency=currency,
            metadata={"operator_id": operator.id, "reason": reason},
        )
    else:
        # Nao converteu: encerra o ciclo levando o funil a EXIT. O historico e
        # a atribuicao continuam valendo para as metricas de campanha.
        user = await session.get(TelegramUser, conversation.telegram_user_id)
        if user is not None:
            try:
                await transition(session, user, FunnelState.EXIT, lead=lead)
            except FunnelError:
                # Estado que nao permite ir a EXIT (ja terminal): o desfecho da
                # conversa vale de qualquer forma.
                pass
        if lead is not None:
            lead.status = LeadStatus.LOST

    conversation.assigned_to = None
    conversation.assigned_at = None
    conversation.status = ConversationStatus.CLOSED
    conversation.ended_at = datetime.now(UTC)
    conversation.outcome = outcome
    conversation.outcome_reason = reason
    conversation.closed_by_operator_id = operator.id

    await record_event(
        session,
        EventType.HUMAN_SUPPORT_CLOSED,
        telegram_user_id=conversation.telegram_user_id,
        lead_id=lead.id if lead else None,
        metadata={
            "operator_id": operator.id,
            "outcome": outcome.value,
            "reason": reason,
            "value": value,
        },
    )
    return conversation
