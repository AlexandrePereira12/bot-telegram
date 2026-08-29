"""Conversas e atendimento humano."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

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
    MessageOut,
    OperatorReply,
)
from app.services import conversation_service
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
    except conversation_service.ConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
    do lead abre um ciclo novo de atendimento.
    """
    try:
        conversation = await conversation_service.close_with_outcome(
            session,
            conversation_id,
            operator,
            outcome=payload.outcome,
            reason=payload.reason,
            value=payload.value,
            currency=payload.currency,
        )
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
        media_path=payload.media_path,
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
        media_path=payload.media_path,
        media_type=payload.media_type.value if payload.media_type else None,
        text=payload.content,
        message_id=message.id,
    )
    return message
