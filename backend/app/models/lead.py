"""Lead e evento do funil."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.enums import EventType, LeadStatus
from app.models.base import TenantMixin, TimestampMixin, UpdatedAtMixin

# JSONB no Postgres; JSON puro no SQLite usado pelos testes.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Lead(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    """Lead do funil.

    Atribuicao (divergencia 4): last_touch e autoritativo para metricas de
    conversao/CPA; first_touch e referencia historica e nunca muda. A coluna
    campaign_id redundante do documento original foi removida.
    """

    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_tenant_status", "tenant_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    first_touch_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    first_touch_ad_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_sets.id", ondelete="SET NULL")
    )
    first_touch_ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id", ondelete="SET NULL"))
    first_touch_source: Mapped[str | None] = mapped_column(String(64))

    last_touch_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    last_touch_ad_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_sets.id", ondelete="SET NULL")
    )
    last_touch_ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id", ondelete="SET NULL"))
    last_touch_source: Mapped[str | None] = mapped_column(String(64))

    source: Mapped[str] = mapped_column(String(64), nullable=False, default="organic")
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, native_enum=False, length=16), nullable=False, default=LeadStatus.NEW
    )
    interest: Mapped[str | None] = mapped_column(String(64))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base, TenantMixin, TimestampMixin):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_tenant_type_created", "tenant_id", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, native_enum=False, length=32), nullable=False, index=True
    )
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONType)
