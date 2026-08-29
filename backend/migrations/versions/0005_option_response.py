"""Resposta propria por opcao de qualificacao.

Antes, toda opcao que levava a INFORMATION recebia o mesmo texto, so trocando
{interest} pelo rotulo. Agora cada opcao pode responder algo diferente — e
com midia propria. Sem resposta configurada, o comportamento anterior
continua valendo.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nulavel: opcao sem resposta propria cai na mensagem generica da etapa,
    # que e exatamente o comportamento de antes desta versao.
    op.add_column("qualification_options", sa.Column("response_body", sa.Text, nullable=True))
    op.add_column(
        "qualification_options", sa.Column("response_media_path", sa.String(255), nullable=True)
    )
    op.add_column(
        "qualification_options", sa.Column("response_media_type", sa.String(16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("qualification_options", "response_media_type")
    op.drop_column("qualification_options", "response_media_path")
    op.drop_column("qualification_options", "response_body")
