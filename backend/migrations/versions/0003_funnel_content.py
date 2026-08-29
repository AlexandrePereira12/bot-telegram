"""Conteudo do funil editavel por campanha.

Textos e opcoes de qualificacao saem do codigo e passam a viver no banco,
com versao por campanha e um padrao global. A migration semeia o conteudo
atual de `app/bot/texts.py` como global, entao o comportamento do bot nao
muda no upgrade e o painel abre com algo para editar.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Conteudo atual de app/bot/texts.py. Copiado literalmente em vez de
# importado: migration precisa ser estavel mesmo que o modulo mude depois.
SEED_CONTENTS: list[tuple[str, str]] = [
    (
        "WELCOME",
        "Ola{name}! Bem-vindo(a) a {company}.\n\n"
        "Antes de continuar, precisamos de dois passos rapidos: confirmar o aceite "
        "dos termos e verificar sua idade.",
    ),
    (
        "CONSENT",
        "**Termos e privacidade (versao {version})**\n\n"
        "Para seguir, precisamos do seu aceite para tratar seus dados e enviar "
        "mensagens sobre este atendimento. Voce pode revogar quando quiser "
        "enviando /parar.\n\nVoce aceita?",
    ),
    (
        "CONSENT_REQUIRED",
        "Sem o aceite dos termos nao conseguimos continuar. "
        "Se mudar de ideia, envie /start novamente.",
    ),
    (
        "AGE_GATE",
        "Este conteudo e restrito a maiores de {min_age} anos.\n\n"
        "Voce confirma que tem {min_age} anos ou mais?",
    ),
    (
        "AGE_REJECTED",
        "Obrigado pela honestidade. Este conteudo e restrito a maiores de "
        "{min_age} anos, entao encerramos por aqui.",
    ),
    ("QUALIFICATION", "Perfeito. Para direcionar melhor, o que voce procura agora?"),
    (
        "INFORMATION",
        "Certo! Reunimos as informacoes sobre *{interest}*.\n\n"
        "Se preferir falar com uma pessoa do time, e so tocar no botao abaixo.",
    ),
    (
        "HUMAN_SUPPORT",
        "Voce entrou na fila de atendimento. Uma pessoa do time responde por aqui "
        "assim que possivel.",
    ),
    (
        "FOLLOWUP",
        "Voce ficou por aqui ha pouco e nao concluiu. "
        "Se ainda quiser continuar, e so responder esta mensagem.",
    ),
]

SEED_OPTIONS: list[tuple[str, str, str, int]] = [
    ("service_info", "Conhecer o servico", "INFORMATION", 10),
    ("faq", "Tirar duvidas", "INFORMATION", 20),
    ("human_support", "Falar com atendente", "HUMAN_SUPPORT", 30),
]


def upgrade() -> None:
    contents = op.create_table(
        "funnel_contents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="CASCADE")),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("media_path", sa.String(255)),
        sa.Column("media_type", sa.String(16)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_funnel_contents_tenant_id", "funnel_contents", ["tenant_id"])
    op.create_index("ix_funnel_contents_campaign_id", "funnel_contents", ["campaign_id"])
    op.create_index(
        "ix_funnel_contents_lookup", "funnel_contents", ["tenant_id", "campaign_id", "step"]
    )
    # NULLS NOT DISTINCT: sem isso o Postgres permitiria varias linhas globais
    # (campaign_id NULL) para a mesma etapa e a resolucao viraria loteria.
    op.execute(
        "ALTER TABLE funnel_contents ADD CONSTRAINT uq_funnel_contents_tenant_campaign_step "
        "UNIQUE NULLS NOT DISTINCT (tenant_id, campaign_id, step)"
    )

    options = op.create_table(
        "qualification_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="CASCADE")),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("target", sa.String(16), nullable=False, server_default="INFORMATION"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_qualification_options_tenant_id", "qualification_options", ["tenant_id"])
    op.create_index(
        "ix_qualification_options_campaign_id", "qualification_options", ["campaign_id"]
    )
    op.create_index(
        "ix_qualification_options_lookup",
        "qualification_options",
        ["tenant_id", "campaign_id", "sort_order"],
    )
    op.execute(
        "ALTER TABLE qualification_options ADD CONSTRAINT "
        "uq_qualification_options_tenant_campaign_key "
        "UNIQUE NULLS NOT DISTINCT (tenant_id, campaign_id, key)"
    )

    # Semeia o padrao global para cada tenant que ja tenha dados. Em um
    # deployment novo a tabela de campanhas esta vazia e o tenant vem do
    # proprio COMPANY_SLUG da aplicacao.
    from app.core.config import settings

    tenant = settings.tenant_id

    op.bulk_insert(
        contents,
        [
            {"tenant_id": tenant, "campaign_id": None, "step": step, "body": body}
            for step, body in SEED_CONTENTS
        ],
    )
    op.bulk_insert(
        options,
        [
            {
                "tenant_id": tenant,
                "campaign_id": None,
                "key": key,
                "label": label,
                "target": target,
                "sort_order": order,
                "is_active": True,
            }
            for key, label, target, order in SEED_OPTIONS
        ],
    )


def downgrade() -> None:
    op.drop_table("qualification_options")
    op.drop_table("funnel_contents")
