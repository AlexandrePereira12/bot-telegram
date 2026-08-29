"""Operador do dashboard (RBAC).

Nao existia no documento original — necessario para conversations.assigned_to
e para os cinco perfis de acesso (planejamento/00-indice.md, divergencia 2).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import OperatorRole
from app.models.base import TenantMixin, TimestampMixin, UpdatedAtMixin


class Operator(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "operators"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_operators_tenant_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[OperatorRole] = mapped_column(
        Enum(OperatorRole, native_enum=False, length=16), nullable=False
    )
    # 2FA obrigatorio para ADMIN. O segredo so e gerado no primeiro acesso,
    # quando o operador escaneia o QR — nunca antecipadamente: segredo criado
    # no `create-admin` circularia por terminal, log e histórico antes de
    # chegar ao dono.
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    # Enquanto for NULL o cadastro do 2FA esta pendente e o login devolve o
    # QR. Preenchido, o 2FA passa a ser exigido e o QR nunca mais e exposto.
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def totp_pending(self) -> bool:
        return self.totp_confirmed_at is None
