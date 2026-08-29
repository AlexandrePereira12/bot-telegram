"""Conversao, consentimento, auditoria e chave de idempotencia."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.lead import JSONType


class Conversion(Base, TenantMixin, TimestampMixin):
    __tablename__ = "conversions"
    __table_args__ = (
        # Dedup deterministico no banco: a mesma conversao externa nunca entra
        # duas vezes, mesmo com webhook reentregue (regras.md, idempotencia).
        UniqueConstraint("tenant_id", "external_id", name="uq_conversions_tenant_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversion_type: Mapped[str] = mapped_column(String(64), nullable=False, default="signup")
    value: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    conversion_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONType)
    converted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConsentRecord(Base, TenantMixin, TimestampMixin):
    """Registro de consentimento versionado.

    Mudanca de termos gera novo registro; revogacao preenche revoked_at e e
    definitiva para aquele registro (reaceitar cria outro).
    """

    __tablename__ = "consent_records"
    __table_args__ = (
        Index("ix_consent_tenant_user_type", "tenant_id", "telegram_user_id", "consent_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(64), nullable=False, default="marketing")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="telegram")
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base, TenantMixin, TimestampMixin):
    """Append-only. A aplicacao nunca atualiza nem apaga linha desta tabela."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    audit_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONType)
    ip_hash: Mapped[str | None] = mapped_column(String(64))


class IdempotencyKey(Base, TenantMixin, TimestampMixin):
    """Chave de idempotencia persistida.

    Fica no PostgreSQL, nao no Redis: SETNX perde a garantia num restart ou
    flush de cache, e a regra exige dedup deterministico.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope", "key", name="uq_idempotency_tenant_scope_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer)
