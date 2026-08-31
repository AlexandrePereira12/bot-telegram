"""Integracao de IA configurada pelo painel.

Uma linha por tenant. A chave de API entra cifrada (`api_key_encrypted`) e sai
mascarada para a tela; o valor em claro so existe em memoria, no momento da
chamada ao provedor.

O atendimento por IA depende desta linha: sem integracao ativa, o funil segue
mandando o lead direto para a fila humana, como sempre fez. E deliberado que a
chave more no banco e nao no `.env` — quem administra a operacao configura pelo
painel, sem precisar de acesso ao servidor nem de um deploy para trocar a chave.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import AiProvider
from app.models.base import TenantMixin, TimestampMixin, UpdatedAtMixin


class AiIntegration(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "ai_integrations"
    __table_args__ = (Index("ix_ai_integrations_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[AiProvider] = mapped_column(
        Enum(AiProvider, native_enum=False, length=16), nullable=False
    )
    #: Chave cifrada com material derivado do ENCRYPTION_KEY. Nunca sai daqui
    #: em claro por nenhuma rota.
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    #: Primeiros e ultimos caracteres, em claro, so para a tela. Guardado
    #: separado para exibir a mascara sem precisar decifrar nada.
    api_key_hint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Resultado do ultimo teste de conexao, para a tela dizer se a integracao
    #: funciona sem obrigar quem administra a mandar mensagem pelo Telegram.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))
