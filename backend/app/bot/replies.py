"""Envio de mensagens do bot com registro em conversations/messages.

Centralizado para que toda saida do bot seja auditavel: nenhuma resposta sai
sem virar linha em `messages` com sender_type=bot.
"""

from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import MediaType, MessageDirection, SenderType
from app.core.logging import get_logger
from app.models import MediaObject, TelegramUser
from app.services import conversation_service, media_service
from app.services.content_service import ResolvedContent

logger = get_logger(__name__)


async def _deliver(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None,
    media: MediaObject | None,
) -> tuple[Message | None, str]:
    """Entrega a mensagem. Retorna (enviada, tipo_registrado).

    A midia sobe como upload de bytes lidos do banco, nunca como URL: o
    servidor do Telegram teria de alcancar a URL, o que nao acontece com
    endereco local. O nome do arquivo vai junto porque `sendVoice` e
    `sendAudio` decidem o tipo por ele.

    Falha no envio da midia cai para texto puro — perder o anexo e melhor que
    travar o funil.
    """
    if media is not None:
        try:
            arquivo = BufferedInputFile(media.content, filename=media.filename())
            if media.media_type == MediaType.PHOTO:
                sent = await message.answer_photo(arquivo, caption=text, reply_markup=markup)
                return sent, "photo"
            if media.media_type == MediaType.VIDEO:
                sent = await message.answer_video(arquivo, caption=text, reply_markup=markup)
                return sent, "video"
            if media.media_type == MediaType.VOICE:
                sent = await message.answer_voice(arquivo, caption=text, reply_markup=markup)
                return sent, "voice"
            if media.media_type == MediaType.AUDIO:
                sent = await message.answer_audio(arquivo, caption=text, reply_markup=markup)
                return sent, "audio"
            logger.warning(
                "tipo de midia desconhecido; caindo para texto",
                extra={"event": "MEDIA_TYPE_UNKNOWN", "type": media.media_type},
            )
        except Exception as exc:
            logger.warning(
                "falha ao enviar midia; caindo para texto",
                extra={"event": "MEDIA_SEND_FAILED", "error": type(exc).__name__},
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
    # Midia carregada aqui, e nao dentro do `_deliver`: e o unico ponto que
    # tem a sessao, e midia apagada do banco simplesmente vira envio de texto.
    media = await media_service.load(session, content.media_id) if content.media_id else None
    if content.media_id and media is None:
        logger.warning(
            "midia configurada nao existe mais",
            extra={"event": "MEDIA_NOT_FOUND", "media_id": content.media_id},
        )

    sent, message_type = await _deliver(message, content.body, markup, media)

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


async def _download_inbound_media(
    session: AsyncSession, message: Message
) -> MediaObject | None:
    """Baixa o anexo recebido e grava como linha de midia, se houver um suportado.

    Sem isso o painel exibiria apenas "o lead mandou uma foto", sem a foto: o
    Telegram guarda o arquivo atras de um `file_id` que expira e exige o token
    do bot, entao o navegador do operador nunca alcancaria a midia.

    Grava na mesma sessao da mensagem de proposito: anexo e mensagem entram
    juntos ou nao entram, e rollback nao deixa objeto orfao no banco.

    Falha aqui nunca derruba o registro da mensagem — a linha entra sem anexo
    e o motivo fica no log. Perder o arquivo e melhor que perder a conversa.
    """
    alvo = (
        message.photo[-1]  # ultima posicao = maior resolucao disponivel
        if message.photo
        else message.video or message.voice or message.audio or message.document
    )
    if alvo is None or message.bot is None:
        return None

    limite = settings.max_media_mb * 1024 * 1024
    if (getattr(alvo, "file_size", None) or 0) > limite:
        logger.warning(
            "anexo recebido acima do limite; registrando sem midia",
            extra={"event": "MEDIA_TOO_LARGE", "bytes": alvo.file_size},
        )
        return None

    try:
        buffer = await message.bot.download(alvo)
        conteudo = buffer.read() if buffer is not None else b""
        return await media_service.save(session, conteudo)
    except media_service.MediaError as exc:
        # Documento de formato que nao exibimos (PDF, zip): registra o texto.
        logger.info(
            "anexo recebido em formato nao suportado",
            extra={"event": "MEDIA_UNSUPPORTED", "reason": str(exc)},
        )
    except Exception as exc:
        logger.warning(
            "falha ao baixar anexo do telegram",
            extra={"event": "MEDIA_DOWNLOAD_FAILED", "error": type(exc).__name__},
        )
    return None


async def record_inbound(
    session: AsyncSession, user: TelegramUser, message: Message
) -> None:
    media = await _download_inbound_media(session, message)
    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.record_message(
        session,
        conversation,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.USER,
        content=message.text or message.caption,
        telegram_message_id=message.message_id,
        message_type=message.content_type,
        media_id=media.id if media else None,
        media_type=media.media_type if media else None,
    )
