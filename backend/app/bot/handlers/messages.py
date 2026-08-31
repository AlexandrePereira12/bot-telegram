"""Mensagens livres do usuario.

Registra tudo e decide quem responde. A ordem das checagens aqui e regra de
negocio, nao estilo: operador atribuido silencia todo o resto (M14), e so
depois disso a IA entra no lugar do texto fixo de fila.
"""

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.commands import resume_funnel
from app.bot.keyboards import humano_keyboard
from app.bot.replies import record_inbound, send
from app.core.enums import (
    EventType,
    FunnelState,
    FunnelStep,
    MessageDirection,
    SenderType,
)
from app.core.logging import get_logger
from app.services import (
    ai_service,
    content_service,
    conversation_service,
    funnel_service,
    lead_service,
)
from app.services.event_service import record_event

router = Router(name="messages")
logger = get_logger(__name__)


async def atender_com_ia(
    message: Message, session: AsyncSession, user, lead
) -> None:
    """Uma rodada do atendimento por IA.

    Escala para a fila humana em dois casos: o lead insistiu em falar com gente,
    ou a IA nao produziu resposta utilizavel (provedor fora, cota estourada,
    texto barrado pelo compliance). Nos dois, quem fala e o texto da etapa
    HUMAN_SUPPORT — o lead nunca fica sem retorno.
    """
    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    lead_id = lead.id if lead else None

    if ai_service.pede_humano(message.text or message.caption):
        await record_event(
            session,
            EventType.AI_HANDOFF_REQUESTED,
            telegram_user_id=user.id,
            lead_id=lead_id,
            metadata={"origem": "texto"},
        )

    if await ai_service.deve_escalar(session, user, conversation):
        await _escalar(message, session, user, lead, motivo="insistencia")
        return

    # `typing...` antes da chamada: e o que faz a espera parecer conversa em
    # vez de travamento. Falhar aqui nao pode derrubar o atendimento.
    try:
        if message.bot is not None and message.chat is not None:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        logger.debug("nao foi possivel enviar o indicador de digitacao")

    campaign_id = lead.last_touch_campaign_id if lead else None
    resposta = await ai_service.responder(
        session, user, conversation, campaign_id, lead_id=lead_id
    )

    if resposta.texto is None:
        await _escalar(message, session, user, lead, motivo=resposta.falha or "falha")
        return

    enviada = await message.answer(resposta.texto, reply_markup=humano_keyboard())
    await conversation_service.record_message(
        session,
        conversation,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.AI,
        content=resposta.texto,
        telegram_message_id=enviada.message_id if enviada else None,
    )


async def _escalar(message: Message, session: AsyncSession, user, lead, motivo: str) -> None:
    """Tira a IA de cena e coloca a conversa na fila humana."""
    try:
        await funnel_service.transition(
            session,
            user,
            FunnelState.HUMAN_SUPPORT,
            lead=lead,
            event=EventType.HUMAN_SUPPORT_REQUESTED,
        )
    except funnel_service.FunnelError:
        # Estado que nao permite ir para atendimento humano (terminal, por
        # exemplo): a conversa segue como esta, e o operador ainda pode assumir
        # pelo painel.
        logger.info(
            "escalada sem transicao de funil",
            extra={"event": "AI_ESCALATED", "reason": motivo},
        )

    # Insistencia e escolha do lead: ele nao precisa ouvir que algo falhou.
    # Qualquer outro motivo e falha nossa, e ai a mensagem explica a espera.
    if motivo != "insistencia":
        await send(message, texts.AI_UNAVAILABLE, session=session, user=user)

    campaign_id = lead.last_touch_campaign_id if lead else None
    conteudo = await content_service.get_content(
        session, FunnelStep.HUMAN_SUPPORT, campaign_id
    )
    await send(message, conteudo, session=session, user=user)

    logger.info(
        "atendimento escalado para humano",
        extra={"event": "AI_ESCALATED", "reason": motivo, "user_id": user.id},
    )


# Anexo sem legenda tambem entra: com o filtro so em texto/legenda, uma foto
# enviada sem nada escrito nao casava com handler nenhum e sumia — nao virava
# linha em `messages` e o operador nunca via que o lead tinha mandado algo.
@router.message(F.text | F.caption | F.photo | F.video | F.voice | F.audio | F.document)
async def on_message(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user, _ = await lead_service.get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await record_inbound(session, user, message)

    if user.is_blocked:
        return

    # Atendimento humano em andamento: nem a automacao nem a IA interferem.
    # Esta checagem vem antes de tudo de proposito — com ela abaixo do trecho
    # da IA, o modelo falaria por cima do operador que ja assumiu a conversa.
    if await conversation_service.is_under_human_support(session, user.id):
        return

    state = FunnelState(user.current_state)

    if user.age_rejected:
        await send(message, texts.age_blocked(), session=session, user=user)
        return

    lead = await lead_service.get_lead_by_user(session, user.id)

    if state == FunnelState.AI_SUPPORT and await ai_service.disponivel(session):
        await atender_com_ia(message, session, user, lead)
        return

    if state in (FunnelState.AI_SUPPORT, FunnelState.HUMAN_SUPPORT):
        # Sem IA (desligada ou ja escalado): o texto de fila de sempre.
        await send(message, texts.UNDER_HUMAN_SUPPORT, session=session, user=user)
        return

    if lead is None:
        await send(message, texts.FALLBACK, session=session, user=user)
        return

    # Mensagem livre no meio do funil: reapresenta a etapa pendente em vez de
    # deixar o usuario travado.
    await resume_funnel(message, session, user, lead)
