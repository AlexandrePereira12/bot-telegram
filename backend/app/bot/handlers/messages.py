"""Mensagens livres do usuario.

Registra tudo e decide se a automacao responde. Enquanto houver operador
atribuido a conversa, o bot fica em silencio (M14).
"""

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.commands import resume_funnel
from app.bot.replies import record_inbound, send
from app.core.enums import FunnelState
from app.core.logging import get_logger
from app.services import conversation_service, lead_service

router = Router(name="messages")
logger = get_logger(__name__)


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

    # Atendimento humano em andamento: a automacao nao interfere.
    if await conversation_service.is_under_human_support(session, user.id):
        return

    state = FunnelState(user.current_state)

    if user.age_rejected:
        await send(message, texts.age_blocked(), session=session, user=user)
        return

    if state == FunnelState.HUMAN_SUPPORT:
        await send(message, texts.UNDER_HUMAN_SUPPORT, session=session, user=user)
        return

    lead = await lead_service.get_lead_by_user(session, user.id)
    if lead is None:
        await send(message, texts.FALLBACK, session=session, user=user)
        return

    # Mensagem livre no meio do funil: reapresenta a etapa pendente em vez de
    # deixar o usuario travado.
    await resume_funnel(message, session, user, lead)
