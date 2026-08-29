"""Desfecho do atendimento.

Encerrar uma conversa passa a exigir um resultado (converteu ou nao), o que
torna respondivel "quantos atendimentos deram certo" por operador e por
campanha. Encerrado, o lead que voltar comeca um ciclo novo.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nulavel: conversa aberta, ou devolvida para a automacao sem encerrar,
    # nao tem desfecho. Conversas ja fechadas antes desta versao ficam sem
    # resultado registrado, o que e fiel — ninguem informou.
    op.add_column("conversations", sa.Column("outcome", sa.String(16), nullable=True))
    op.add_column("conversations", sa.Column("outcome_reason", sa.String(255), nullable=True))
    op.add_column(
        "conversations",
        sa.Column(
            "closed_by_operator_id",
            sa.Integer,
            sa.ForeignKey("operators.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_tenant_outcome", "conversations", ["tenant_id", "outcome"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_tenant_outcome", table_name="conversations")
    op.drop_column("conversations", "closed_by_operator_id")
    op.drop_column("conversations", "outcome_reason")
    op.drop_column("conversations", "outcome")
