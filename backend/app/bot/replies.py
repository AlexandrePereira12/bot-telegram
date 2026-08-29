"""Envio de mensagens do bot com registro em conversations/messages.

Centralizado para que toda saida do bot seja auditavel: nenhuma resposta sai
sem virar linha em `messages` com sender_type=bot.
"""

from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import MediaType, MessageDirection, SenderType
from app.core.logging import get_logger
from app.models import TelegramUser
from app.services import conversation_service
from app.services.content_service import ResolvedContent

logger = get_logger(__name__)


async def _deliver(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None,
    media_path: str | None,
    media_type: MediaType | None,
) -> tuple[Message | None, str]:
    """Entrega a mensagem. Retorna (enviada, tipo_registrado).

    A midia vai como arquivo do disco (FSInputFile), nunca como URL: o
    servidor do Telegram teria de alcancar a URL, o que nao acontece com
    endereco local nem com volume privado.

    Falha no envio da midia cai para texto puro — perder o anexo e melhor que
    travar o funil.
    """
    if media_path and media_type:
        full = Path(settings.media_root) / media_path
        if full.is_file():
            try:
                file = FSInputFile(str(full))
                if media_type == MediaType.PHOTO:
                    sent = await message.answer_photo(
                        file, caption=text, reply_markup=markup
                    )
                    return sent, "photo"
                sent = await message.answer_video(file, caption=text, reply_markup=markup)
                return sent, "video"
            except Exception as exc:
                logger.warning(
                    "falha ao enviar midia; caindo para texto",
                    extra={"event": "MEDIA_SEND_FAILED", "error": type(exc).__name__},
                )
        else:
            logger.warning(
                "midia configurada nao existe no volume",
                extra={"event": "MEDIA_NOT_FOUND", "path": media_path},
            )

    sent = await message.answer(text, reply_markup=markup)
    return sent, "text"


async def send(
    message: Message,
    content: ResolvedContent | str,
    *,
    session: AsyncSession,
    user: TelegramUser,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Envia e registra. Aceita texto puro ou conteudo resolvido com midia."""
    if isinstance(content, str):
        content = ResolvedContent(body=content)

    # Envia antes de registrar de proposito: o envio ao Telegram e o passo
    # irreversivel e precisa do message_id de retorno. Se o registro falhar
    # depois, a transacao do update inteiro sofre rollback e o proximo /start
    # reapresenta a etapa — preferivel a gravar mensagem que nunca saiu.
    sent, message_type = await _deliver(
        message, content.body, markup, content.media_path, content.media_type
    )

    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.record_message(
        session,
        conversation,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.BOT,
        content=content.body,
        telegram_message_id=sent.message_id if sent else None,
        message_type=message_type,
    )


async def record_inbound(
    session: AsyncSession, user: TelegramUser, message: Message
) -> None:
    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.record_message(
        session,
        conversation,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.USER,
        content=message.text or message.caption,
        telegram_message_id=message.message_id,
        message_type=message.content_type,
    )
