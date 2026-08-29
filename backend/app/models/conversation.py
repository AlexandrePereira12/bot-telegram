"""Conversa e mensagem."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import (
    ConversationOutcome,
    ConversationStatus,
    MediaType,
    MessageDirection,
    SenderType,
)
from app.models.base import TenantMixin, TimestampMixin


class Conversation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_tenant_status", "tenant_id", "status"),
        Index("ix_conversations_tenant_outcome", "tenant_id", "outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, native_enum=False, length=16),
        nullable=False,
        default=ConversationStatus.OPEN,
    )
    # Enquanto nao for NULL, a automacao nao responde este usuario.
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Desfecho do atendimento. NULL enquanto aberto ou apenas devolvido para a
    # automacao — so o encerramento exige um resultado.
    outcome: Mapped[ConversationOutcome | None] = mapped_column(
        Enum(ConversationOutcome, native_enum=False, length=16)
    )
    outcome_reason: Mapped[str | None] = mapped_column(String(255))
    # Quem encerrou pode nao ser quem estava atendendo.
    closed_by_operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL")
    )


class Message(Base, TenantMixin, TimestampMixin):
    """Mensagem trocada.

    sender_type/sender_id nao existiam no documento original (divergencia 8):
    sem eles nao da para distinguir mensagem do bot de mensagem de operador.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_tenant_conversation", "tenant_id", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, native_enum=False, length=16), nullable=False
    )
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, native_enum=False, length=16), nullable=False
    )
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id", ondelete="SET NULL"))
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    content: Mapped[str | None] = mapped_column(Text)
    #: Anexo da mensagem, relativo ao volume de midia.
    media_path: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[MediaType | None] = mapped_column(
        Enum(MediaType, native_enum=False, length=16)
    )
