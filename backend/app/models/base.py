"""Mixins comuns a todos os modelos."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class TenantMixin:
    """tenant_id em toda tabela.

    Nesta arquitetura ha um banco por empresa, entao o valor e constante por
    deployment. A coluna existe desde o inicio para que a migracao a
    multi-tenant real (varias empresas no mesmo cluster) nao exija reescrever
    o schema. NOT NULL de proposito: coluna anulavel seria esquecida nas
    queries e viraria vazamento silencioso entre tenants.
    """

    @staticmethod
    def _default_tenant() -> str:
        return settings.tenant_id

    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, default=_default_tenant
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )
