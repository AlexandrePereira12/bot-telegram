"""Campanha, conjunto de anuncios, anuncio e tracking token."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import EntityStatus
from app.models.base import TenantMixin, TimestampMixin, UpdatedAtMixin


class Campaign(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_campaigns_tenant_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False, length=16),
        nullable=False,
        default=EntityStatus.ACTIVE,
    )
    # Investimento so e usado em CPL/CPA/ROI quando informado; sem dado de
    # midia o dashboard omite a metrica em vez de assumir zero.
    spend: Mapped[float | None] = mapped_column(Numeric(14, 2))
    impressions: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)


class AdSet(Base, TenantMixin, TimestampMixin):
    __tablename__ = "ad_sets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_ad_sets_tenant_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False, length=16),
        nullable=False,
        default=EntityStatus.ACTIVE,
    )


class Ad(Base, TenantMixin, TimestampMixin):
    __tablename__ = "ads"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_ads_tenant_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ad_set_id: Mapped[int] = mapped_column(
        ForeignKey("ad_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    creative: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False, length=16),
        nullable=False,
        default=EntityStatus.ACTIVE,
    )


class TrackingToken(Base, TenantMixin, TimestampMixin):
    """Ponto de entrada do funil.

    Nao existia no modelo do documento original (divergencia 1). O token e
    opaco: nao carrega campaign_id nem qualquer dado interno, e pode ser
    revogado sem afetar os demais.
    """

    __tablename__ = "tracking_tokens"
    __table_args__ = (
        Index("ix_tracking_tokens_tenant_token", "tenant_id", "token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Unico globalmente: e um segredo opaco, nao um identificador por tenant.
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ad_set_id: Mapped[int | None] = mapped_column(ForeignKey("ad_sets.id", ondelete="SET NULL"))
    ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    label: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
