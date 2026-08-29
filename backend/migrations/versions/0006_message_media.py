"""Anexo em mensagem do atendimento.

O operador passa a poder mandar imagem ou video pelo chat do painel. O
arquivo vive no mesmo volume de midia do conteudo do funil e sai como bytes
para o Telegram.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("media_path", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("media_type", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "media_type")
    op.drop_column("messages", "media_path")
