"""Usuario do Telegram.

Renomeado de `users` do documento original para nao colidir com o operador
do dashboard (planejamento/00-indice.md, divergencia 2).
"""

from sqlalchemy import BigInteger, Boolean, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import ConsentStatus, FunnelState
from app.models.base import TenantMixin, TimestampMixin, UpdatedAtMixin


class TelegramUser(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "telegram_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "telegram_id", name="uq_telegram_users_tenant_tg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(8))

    current_state: Mapped[FunnelState] = mapped_column(
        Enum(FunnelState, native_enum=False, length=32),
        nullable=False,
        default=FunnelState.NEW,
    )
    # Age gate: persistido no usuario, nao apenas no handler que perguntou.
    # Todo acesso a QUALIFICATION reconsulta este campo (regras.md).
    age_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    age_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus, native_enum=False, length=16),
        nullable=False,
        default=ConsentStatus.PENDING,
    )
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
