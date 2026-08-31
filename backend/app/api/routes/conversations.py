"""Conversas e atendimento humano."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, client_ip, require
from app.core.config import settings
from app.core.enums import ConversationStatus, MessageDirection, SenderType
from app.core.logging import get_logger
from app.core.security import hash_ip
from app.models import Conversation, Message, Operator, TelegramUser
from app.schemas import (
    CloseRequest,
    ConversationDetail,
    ConversationOut,
    MediaUploadOut,
    MessageOut,
    OperatorReply,
)
from app.services import conversation_service, media_service
from app.services.event_service import record_audit
from app.services.lead_service import get_lead_by_user

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = get_logger(__name__)

ConvRead = Depends(require("conversations:read"))
ConvWrite = Depends(require("conversations:write"))


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    session: SessionDep,
    _: Operator = ConvRead,
    status_filter: ConversationStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.tenant_id == settings.tenant_id)
    if status_filter:
        stmt = stmt.where(Conversation.status == status_filter)
    stmt = stmt.order_by(Conversation.id.desc()).limit(min(limit, 500)).offset(offset)
    return list((await session.execute(stmt)).scalars())


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int, session: SessionDep, _: Operator = ConvRead
) -> ConversationDetail:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="conversa nao encontrada")

    messages = (
        await session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.tenant_id == settings.tenant_id,
            )
            .order_by(Message.id)
        )
    ).scalars()

    detail = ConversationDetail.model_validate(conversation)
    detail.messages = [MessageOut.model_validate(m) for m in messages]

    user = await session.get(TelegramUser, conversation.telegram_user_id)
    if user is not None:
        detail.telegram_username = user.username
    lead = await get_lead_by_user(session, conversation.telegram_user_id)
    detail.lead_id = lead.id if lead else None
    return detail


@router.post("/{conversation_id}/assign", response_model=ConversationOut)
async def assign_conversation(
    conversation_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = ConvWrite,
) -> Conversation:
    try:
        conversation = await conversation_service.assign(session, conversation_id, operator)
    except conversation_service.ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except conversation_service.ConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="assign",
        resource_type="conversation",
        resource_id=conversation.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return conversation


@router.post("/{conversation_id}/release", response_model=ConversationOut)
async def release_conversation(
    conversation_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = ConvWrite,
) -> Conversation:
    """Devolve para a automacao sem encerrar — o atendimento segue aberto."""
    try:
        conversation = await conversation_service.release(session, conversation_id, operator)
    except conversation_service.ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except conversation_service.ConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="release",
        resource_type="conversation",
        resource_id=conversation.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return conversation


@router.post("/{conversation_id}/close", response_model=ConversationOut)
async def close_conversation(
    conversation_id: int,
    payload: CloseRequest,
    request: Request,
    session: SessionDep,
    operator: Operator = ConvWrite,
) -> Conversation:
    """Encerra o atendimento registrando se deu certo ou nao.

    Desfecho convertido gera a conversao (dedup por conversa, entao clicar
    duas vezes nao duplica a metrica). Depois de encerrado, uma mensagem nova
    do lead abre um ciclo novo de atendimento — ou o operador reabre este
    mesmo pelo `/reopen`.

    A despedida, quando informada, e registrada dentro do atendimento e
    enfileirada apos o commit: mensagem enviada ao lead sem o encerramento ter
    sido gravado seria o pior dos dois mundos.
    """
    from app.workers.queue import enqueue

    user = await _telegram_user(session, conversation_id)

    try:
        conversation = await conversation_service.close_with_outcome(
            session,
            conversation_id,
            operator,
            outcome=payload.outcome,
            reason=payload.reason,
            value=payload.value,
            currency=payload.currency,
            farewell=payload.farewell if user is not None and not user.is_blocked else None,
        )
    except conversation_service.ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except conversation_service.ConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="close",
        resource_type="conversation",
        resource_id=conversation.id,
        metadata={"outcome": payload.outcome.value, "value": payload.value},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()

    despedida = payload.farewell.strip() if payload.farewell else ""
    if despedida and user is not None and not user.is_blocked:
        await enqueue("send_telegram_message", telegram_id=user.telegram_id, text=despedida)
    elif despedida:
        logger.warning(
            "despedida nao enviada: usuario indisponivel",
            extra={"event": "FAREWELL_SKIPPED", "conversation_id": conversation_id},
        )
    return conversation


@router.post("/{conversation_id}/reopen", response_model=ConversationOut)
async def reopen_conversation(
    conversation_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = ConvWrite,
) -> Conversation:
    """Reabre um atendimento encerrado e devolve para a fila.

    Sem isso, corrigir um encerramento errado dependia de o lead escrever de
    novo. O desfecho volta a ser NULL, o historico permanece e a conversao ja
    registrada continua valendo.
    """
    try:
        conversation = await conversation_service.reopen(session, conversation_id, operator)
    except conversation_service.ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except conversation_service.ConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="reopen",
        resource_type="conversation",
        resource_id=conversation.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return conversation


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: int,
    payload: OperatorReply,
    request: Request,
    session: SessionDep,
    operator: Operator = ConvWrite,
) -> Message:
    """Operador responde no Telegram.

    Exige que a conversa esteja atribuida a este operador: evita dois
    atendentes falando ao mesmo tempo com o mesmo lead.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="conversa nao encontrada")
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="atendimento encerrado")
    if conversation.assigned_to != operator.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="assuma a conversa antes de responder",
        )

    user = await session.get(TelegramUser, conversation.telegram_user_id)
    if user is None or user.is_blocked:
        raise HTTPException(status_code=409, detail="usuario indisponivel")

    # Envio efetivo pelo Telegram roda no worker: a API nao bloqueia em I/O
    # externo nem falha a requisicao se a API do Telegram estiver instavel.
    from app.workers.queue import enqueue

    message = await conversation_service.record_message(
        session,
        conversation,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.OPERATOR,
        sender_id=operator.id,
        content=payload.content,
        message_type=payload.media_type.value if payload.media_type else "text",
        media_id=payload.media_id,
        media_type=payload.media_type,
    )
    await record_audit(
        session,
        actor_id=operator.id,
        action="reply",
        resource_type="conversation",
        resource_id=conversation.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    await session.refresh(message)

    await enqueue(
        "send_telegram_message",
        telegram_id=user.telegram_id,
        media_id=payload.media_id,
        text=payload.content,
        message_id=message.id,
    )
    return message


async def _telegram_user(session: AsyncSession, conversation_id: int) -> TelegramUser | None:
    """Usuario do Telegram por tras da conversa, se ela existir neste tenant."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        return None
    return await session.get(TelegramUser, conversation.telegram_user_id)


@router.post(
    "/{conversation_id}/media",
    response_model=MediaUploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_conversation_media(
    conversation_id: int,
    request: Request,
    session: SessionDep,
    file: UploadFile = File(...),
    kind: str = Form(default=""),
    operator: Operator = ConvWrite,
) -> MediaUploadOut:
    """Recebe o anexo que o operador vai mandar no chat.

    Existe separado de `/content/media` por causa da autorizacao: aquele exige
    `campaigns:write`, que so ADMIN e MANAGER tem — ou seja, o clipe do chat
    respondia 403 justamente para OPERATOR e SUPPORT, que sao quem atende.
    Aqui a guarda e `conversations:write`, e o alcance e o chat: quem anexa uma
    imagem numa conversa nao ganha com isso o direito de editar o funil.

    `kind=voice` marca gravacao feita no navegador, que chega em WebM/Opus ou
    MP4/AAC e precisa virar OGG/Opus antes de existir como mensagem de voz.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="conversa nao encontrada")

    content = await file.read()
    try:
        if kind == "voice":
            content = await media_service.transcode_voice(content)
        media = await media_service.save(session, content)
    except media_service.MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await record_audit(
        session,
        actor_id=operator.id,
        action="upload",
        resource_type="media",
        resource_id=media.id,
        metadata={
            "type": media.media_type.value,
            "bytes": media.size_bytes,
            "conversation_id": conversation_id,
        },
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
    return MediaUploadOut(
        media_id=media.id, media_type=media.media_type, size_bytes=media.size_bytes
    )


@router.get("/{conversation_id}/messages/{message_id}/media")
async def get_message_media(
    conversation_id: int,
    message_id: int,
    session: SessionDep,
    _: Operator = ConvRead,
) -> Response:
    """Entrega o anexo de uma mensagem para o painel.

    O endereco e o id da mensagem, nunca o do objeto de midia: a autorizacao
    sai por conversa, e ninguem varre `media_objects` por id sequencial. O
    conteudo vem do banco — nao ha volume publicado, nem arquivo em disco.
    """
    message = await session.get(Message, message_id)
    if (
        message is None
        or message.tenant_id != settings.tenant_id
        or message.conversation_id != conversation_id
        or message.media_id is None
    ):
        raise HTTPException(status_code=404, detail="anexo nao encontrado")

    media = await media_service.load(session, message.media_id)
    if media is None:
        logger.warning(
            "anexo referenciado nao existe mais",
            extra={"event": "MEDIA_NOT_FOUND", "message_id": message_id},
        )
        raise HTTPException(status_code=404, detail="anexo indisponivel")

    return Response(
        content=media.content,
        media_type=media.content_type,
        # Sem cache no disco do navegador: o painel promete que desativar um
        # operador tem efeito imediato, e anexo cacheado continuaria abrindo
        # depois do acesso cortado. O custo e um fetch por abertura da
        # conversa — o refetch de 10s nao remonta a bolha, entao nao repete.
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/{conversation_id}/media", status_code=status.HTTP_204_NO_CONTENT)
async def discard_conversation_media(
    conversation_id: int,
    media_id: int,
    request: Request,
    session: SessionDep,
    operator: Operator = ConvWrite,
) -> None:
    """Descarta um anexo que subiu mas nao foi enviado.

    Sem isso, cada anexo trocado ou cada gravacao descartada deixava uma linha
    de midia no banco sem nenhuma mensagem apontando para ela — peso que so
    cresce e que ninguem sabe distinguir do que esta em uso.

    Anexo ja referenciado por uma mensagem nunca e removido: apagar a midia
    de uma mensagem entregue deixaria a conversa com um buraco no historico.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=404, detail="conversa nao encontrada")

    em_uso = (
        await session.execute(
            select(Message.id)
            .where(
                Message.tenant_id == settings.tenant_id,
                Message.media_id == media_id,
            )
            .limit(1)
        )
    ).first()
    if em_uso is not None:
        raise HTTPException(status_code=409, detail="anexo ja enviado em uma mensagem")

    # `delete` so encontra midia deste tenant, entao id de outra empresa cai
    # aqui como inexistente em vez de ser apagado.
    if not await media_service.delete(session, media_id):
        raise HTTPException(status_code=404, detail="anexo nao encontrado")

    await record_audit(
        session,
        actor_id=operator.id,
        action="discard",
        resource_type="media",
        resource_id=media_id,
        metadata={"conversation_id": conversation_id},
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()
