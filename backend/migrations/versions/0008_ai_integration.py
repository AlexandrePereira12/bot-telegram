"""Integracao de IA configurada pelo painel.

A chave de API deixa de vir do `.env` e passa a viver no banco, cifrada. Motivo:
quem administra a operacao precisa trocar a chave sem acesso ao servidor e sem
deploy — e uma decisao de operacao, nao de infraestrutura.

Cifrada, e nao hasheada: o bot usa a chave para chamar o provedor, entao ela
precisa voltar ao claro. O que a tela mostra e uma mascara montada a partir de
`api_key_hint`, que guarda so as pontas.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_hint", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_integrations_tenant", "ai_integrations", ["tenant_id"])
    op.create_index("ix_ai_integrations_tenant_id", "ai_integrations", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_integrations_tenant_id", "ai_integrations")
    op.drop_index("ix_ai_integrations_tenant", "ai_integrations")
    op.drop_table("ai_integrations")
