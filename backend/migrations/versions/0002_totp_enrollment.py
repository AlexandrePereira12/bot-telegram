"""Cadastro de 2FA no primeiro acesso.

O segredo TOTP deixa de ser gerado na criacao do operador e passa a nascer no
primeiro login, quando o dono escaneia o QR. `totp_confirmed_at` marca o
cadastro concluido: enquanto for NULL o login devolve o QR; preenchido, o
codigo de 6 digitos passa a ser exigido.

Segredos gerados pelo fluxo antigo sao apagados: circularam por terminal e
log antes de chegar ao dono, entao valem como comprometidos.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operators",
        sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Invalida os segredos do fluxo antigo: quem tinha 2FA passa a refazer o
    # cadastro no proximo login, com segredo novo.
    op.execute("UPDATE operators SET totp_secret = NULL")


def downgrade() -> None:
    op.drop_column("operators", "totp_confirmed_at")
