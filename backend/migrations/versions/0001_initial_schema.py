"""Schema inicial.

Ja nasce com as correcoes registradas em planejamento/00-indice.md:
tracking_tokens existe, users virou telegram_users, operators existe,
tenant_id NOT NULL em todas as tabelas, leads sem campaign_id redundante e
messages com sender_type/sender_id.

Revision ID: 0001
Revises:
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = sa.Column("tenant_id", sa.String(64), nullable=False)


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", sa.String(64), nullable=False)


def _created() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _updated() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(128)),
        sa.Column("language", sa.String(8)),
        sa.Column("current_state", sa.String(32), nullable=False, server_default="NEW"),
        sa.Column("age_confirmed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("age_rejected", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("consent_status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("is_blocked", sa.Boolean, nullable=False, server_default=sa.false()),
        _created(),
        _updated(),
        sa.UniqueConstraint("tenant_id", "telegram_id", name="uq_telegram_users_tenant_tg"),
    )
    op.create_index("ix_telegram_users_tenant_id", "telegram_users", ["tenant_id"])
    op.create_index("ix_telegram_users_telegram_id", "telegram_users", ["telegram_id"])

    op.create_table(
        "operators",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(128)),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("totp_secret", sa.String(64)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        _created(),
        _updated(),
        sa.UniqueConstraint("tenant_id", "email", name="uq_operators_tenant_email"),
    )
    op.create_index("ix_operators_tenant_id", "operators", ["tenant_id"])
    op.create_index("ix_operators_email", "operators", ["email"])

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column("external_id", sa.String(128)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("platform", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("spend", sa.Numeric(14, 2)),
        sa.Column("impressions", sa.Integer),
        sa.Column("clicks", sa.Integer),
        _created(),
        _updated(),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_campaigns_tenant_external"),
    )
    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"])

    op.create_table(
        "ad_sets",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "campaign_id",
            sa.Integer,
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        _created(),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_ad_sets_tenant_external"),
    )
    op.create_index("ix_ad_sets_tenant_id", "ad_sets", ["tenant_id"])
    op.create_index("ix_ad_sets_campaign_id", "ad_sets", ["campaign_id"])

    op.create_table(
        "ads",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "ad_set_id",
            sa.Integer,
            sa.ForeignKey("ad_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("creative", sa.String(512)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        _created(),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_ads_tenant_external"),
    )
    op.create_index("ix_ads_tenant_id", "ads", ["tenant_id"])
    op.create_index("ix_ads_ad_set_id", "ads", ["ad_set_id"])

    # Ponto de entrada do funil. Nao existia no documento original.
    op.create_table(
        "tracking_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "campaign_id",
            sa.Integer,
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ad_set_id", sa.Integer, sa.ForeignKey("ad_sets.id", ondelete="SET NULL")),
        sa.Column("ad_id", sa.Integer, sa.ForeignKey("ads.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("label", sa.String(255)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        _created(),
    )
    op.create_index("ix_tracking_tokens_tenant_id", "tracking_tokens", ["tenant_id"])
    op.create_index("ix_tracking_tokens_tenant_token", "tracking_tokens", ["tenant_id", "token"])
    op.create_index("ix_tracking_tokens_campaign_id", "tracking_tokens", ["campaign_id"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "telegram_user_id",
            sa.Integer,
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "first_touch_campaign_id",
            sa.Integer,
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "first_touch_ad_set_id", sa.Integer, sa.ForeignKey("ad_sets.id", ondelete="SET NULL")
        ),
        sa.Column("first_touch_ad_id", sa.Integer, sa.ForeignKey("ads.id", ondelete="SET NULL")),
        sa.Column("first_touch_source", sa.String(64)),
        sa.Column(
            "last_touch_campaign_id",
            sa.Integer,
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "last_touch_ad_set_id", sa.Integer, sa.ForeignKey("ad_sets.id", ondelete="SET NULL")
        ),
        sa.Column("last_touch_ad_id", sa.Integer, sa.ForeignKey("ads.id", ondelete="SET NULL")),
        sa.Column("last_touch_source", sa.String(64)),
        sa.Column("source", sa.String(64), nullable=False, server_default="organic"),
        sa.Column("status", sa.String(16), nullable=False, server_default="NEW"),
        sa.Column("interest", sa.String(64)),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True)),
        _created(),
        _updated(),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_telegram_user_id", "leads", ["telegram_user_id"])
    op.create_index("ix_leads_last_touch_campaign_id", "leads", ["last_touch_campaign_id"])
    op.create_index("ix_leads_tenant_status", "leads", ["tenant_id", "status"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "telegram_user_id",
            sa.Integer,
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
        ),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("metadata", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")),
        _created(),
    )
    op.create_index("ix_events_tenant_id", "events", ["tenant_id"])
    op.create_index("ix_events_telegram_user_id", "events", ["telegram_user_id"])
    op.create_index("ix_events_lead_id", "events", ["lead_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index(
        "ix_events_tenant_type_created", "events", ["tenant_id", "event_type", "created_at"]
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "telegram_user_id",
            sa.Integer,
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", sa.Integer, sa.ForeignKey("operators.id", ondelete="SET NULL")),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        _created(),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_telegram_user_id", "conversations", ["telegram_user_id"])
    op.create_index("ix_conversations_assigned_to", "conversations", ["assigned_to"])
    op.create_index("ix_conversations_tenant_status", "conversations", ["tenant_id", "status"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger),
        sa.Column("direction", sa.String(16), nullable=False),
        # sender_type/sender_id: distinguem bot, usuario e operador humano.
        sa.Column("sender_type", sa.String(16), nullable=False),
        sa.Column("sender_id", sa.Integer, sa.ForeignKey("operators.id", ondelete="SET NULL")),
        sa.Column("message_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column("content", sa.Text),
        _created(),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_tenant_conversation", "messages", ["tenant_id", "conversation_id", "created_at"]
    )

    op.create_table(
        "conversions",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "lead_id", sa.Integer, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("conversion_type", sa.String(64), nullable=False, server_default="signup"),
        sa.Column("value", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("metadata", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")),
        sa.Column(
            "converted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        _created(),
        # Dedup deterministico da conversao externa.
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_conversions_tenant_external"),
    )
    op.create_index("ix_conversions_tenant_id", "conversions", ["tenant_id"])
    op.create_index("ix_conversions_lead_id", "conversions", ["lead_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column(
            "telegram_user_id",
            sa.Integer,
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(64), nullable=False, server_default="marketing"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("accepted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(64), nullable=False, server_default="telegram"),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        _created(),
    )
    op.create_index("ix_consent_records_tenant_id", "consent_records", ["tenant_id"])
    op.create_index("ix_consent_records_telegram_user_id", "consent_records", ["telegram_user_id"])
    op.create_index(
        "ix_consent_tenant_user_type",
        "consent_records",
        ["tenant_id", "telegram_user_id", "consent_type"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("operators.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("result", sa.String(32), nullable=False, server_default="success"),
        sa.Column("metadata", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")),
        sa.Column("ip_hash", sa.String(64)),
        _created(),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_tenant_created", "audit_logs", ["tenant_id", "created_at"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        _tenant(),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("response_code", sa.Integer),
        _created(),
        sa.UniqueConstraint(
            "tenant_id", "scope", "key", name="uq_idempotency_tenant_scope_key"
        ),
    )
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])


def downgrade() -> None:
    for table in (
        "idempotency_keys",
        "audit_logs",
        "consent_records",
        "conversions",
        "messages",
        "conversations",
        "events",
        "leads",
        "tracking_tokens",
        "ads",
        "ad_sets",
        "campaigns",
        "operators",
        "telegram_users",
    ):
        op.drop_table(table)
