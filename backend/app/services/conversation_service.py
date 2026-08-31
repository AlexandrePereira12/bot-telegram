"""Conversas e atendimento humano (M13, M14, CU2)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    TERMINAL_STATES,
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
from app.services.funnel_service import reopen as reopen_funnel  # ciclo novo, nao transicao
from app.services.lead_service import get_lead_by_user

logger = get_logger(__name__)


class ConversationError(Exception):
    pass


class ConversationNotFound(ConversationError):
    """Conversa inexistente ou de outro tenant.

    Separada do conflito de estado para que a API responda 404 onde o recurso
    nao existe e 409 onde existe mas a operacao nao cabe — antes as duas
    coisas chegavam como o mesmo erro e cada rota escolhia um codigo.
    """


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
    media_id: int | None = None,
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
        media_id=media_id,
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
        raise ConversationNotFound("conversa inexistente")
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
        raise ConversationNotFound("conversa inexistente")

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
    farewell: str | None = None,
) -> Conversation:
    """Encerra o atendimento registrando o desfecho.

    Convertido passa por `register_conversion`, para que o evento CONVERSION,
    o `converted_at` e a atribuicao por last touch aconteçam num lugar so. O
    `external_id` e deterministico (`manual:<id da conversa>`), entao clicar
    duas vezes em encerrar cai na constraint unica de conversoes e nao
    duplica a metrica.

    Depois de encerrada, uma mensagem nova do lead abre outro ciclo — ver
    `funnel_service.reopen`.

    `farewell` e a ultima mensagem enviada ao lead. Fica registrada aqui, antes
    da mudanca de status, para que o historico mostre a despedida dentro do
    atendimento que ela encerrou — e nao solta depois dele. O envio em si e do
    worker, como qualquer outra resposta do operador.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise ConversationNotFound("conversa inexistente")
    if conversation.status == ConversationStatus.CLOSED:
        raise ConversationError("atendimento ja encerrado")

    if farewell and farewell.strip():
        await record_message(
            session,
            conversation,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.OPERATOR,
            sender_id=operator.id,
            content=farewell.strip(),
        )

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


async def reopen(
    session: AsyncSession, conversation_id: int, operator: Operator
) -> Conversation:
    """Reabre um atendimento encerrado, sem esperar o lead escrever.

    Existe porque encerrar e uma decisao humana e humano erra: fechar no
    atendimento errado, marcar o desfecho trocado, ou o lead voltar por outro
    canal. Sem isso a unica saida era esperar uma mensagem nova, e o ciclo
    perdido virava um atendimento a mais nas metricas.

    O que a reabertura faz e desfazer o encerramento — o desfecho volta a ser
    NULL e a conversa retorna para a fila como OPEN, sem atribuicao: quem
    reabriu nao necessariamente vai atender. O que ela NAO faz e apagar
    historico: as mensagens continuam, e uma conversao ja registrada continua
    valendo. Encerrar de novo como convertido cai no mesmo `external_id`
    (`manual:<id>`) e nao gera segunda conversao — reabrir nao e caminho para
    contar a mesma venda duas vezes.

    O funil tambem volta, quando o lead permite: quem foi reprovado no age
    gate ou nunca aceitou os termos segue de fora, e nesse caso so a conversa
    reabre.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise ConversationNotFound("conversa inexistente")
    if conversation.status != ConversationStatus.CLOSED:
        raise ConversationError("atendimento nao esta encerrado")

    outcome_anterior = conversation.outcome.value if conversation.outcome else None

    conversation.status = ConversationStatus.OPEN
    conversation.assigned_to = None
    conversation.assigned_at = None
    conversation.ended_at = None
    conversation.outcome = None
    conversation.outcome_reason = None
    conversation.closed_by_operator_id = None

    lead = await get_lead_by_user(session, conversation.telegram_user_id)
    user = await session.get(TelegramUser, conversation.telegram_user_id)
    funil_reaberto = False
    if user is not None and FunnelState(user.current_state) in TERMINAL_STATES:
        try:
            await reopen_funnel(session, user, lead)
            funil_reaberto = True
        except FunnelError as exc:
            logger.info(
                "conversa reaberta sem reabrir o funil",
                extra={"event": "FUNNEL_REOPEN_SKIPPED", "reason": str(exc)},
            )

    await record_event(
        session,
        EventType.HUMAN_SUPPORT_REOPENED,
        telegram_user_id=conversation.telegram_user_id,
        lead_id=lead.id if lead else None,
        metadata={
            "operator_id": operator.id,
            "previous_outcome": outcome_anterior,
            "funnel_reopened": funil_reaberto,
        },
    )
    return conversation
