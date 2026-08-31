"""Midia sai do volume e passa a viver no banco.

Antes, o arquivo ficava num volume do Docker e a linha guardava so o caminho.
Backup do PostgreSQL nao levava o anexo junto: restaurar o dump devolvia a
conversa com `media_path` apontando para arquivo inexistente — buraco no
historico, sem erro em lugar nenhum. Agora os bytes ficam em `media_objects`,
e o dump e o backup inteiro do atendimento.

Esta migration COPIA o que existe no volume para dentro do banco. Se alguma
linha referenciar arquivo ilegivel, ela ABORTA em vez de gravar NULL: perder
anexo em silencio e exatamente o que a mudanca quer evitar. Por isso o volume
precisa continuar montado no momento do upgrade — ele so pode sair do compose
depois que esta migration tiver rodado em todas as instalacoes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-30
"""

import os
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Onde o volume estava montado. Lido do ambiente para o upgrade funcionar
#: tanto no container quanto numa execucao local apontando para outra pasta.
MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/app/media")

CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}

#: (tabela, coluna de caminho, coluna de tipo, coluna nova de referencia)
REFERENCIAS = [
    ("messages", "media_path", "media_type", "media_id"),
    ("funnel_contents", "media_path", "media_type", "media_id"),
    (
        "qualification_options",
        "response_media_path",
        "response_media_type",
        "response_media_id",
    ),
]


def _importar(connection: sa.Connection) -> None:
    """Le cada arquivo referenciado e grava como linha de `media_objects`.

    O mesmo caminho pode aparecer em varias linhas (o painel reaproveita a
    midia ao duplicar conteudo), entao o arquivo e lido uma vez so e o id
    resultante e reusado.
    """
    ids_por_caminho: dict[str, int] = {}
    raiz = Path(MEDIA_ROOT)

    for tabela, coluna_path, coluna_tipo, coluna_id in REFERENCIAS:
        linhas = connection.execute(
            sa.text(
                f"SELECT id, tenant_id, {coluna_path} AS caminho, "  # noqa: S608
                f"{coluna_tipo} AS tipo FROM {tabela} WHERE {coluna_path} IS NOT NULL"
            )
        ).fetchall()

        for linha in linhas:
            caminho = linha.caminho
            if caminho not in ids_por_caminho:
                arquivo = raiz / caminho
                if not arquivo.is_file():
                    raise RuntimeError(
                        f"midia ausente no volume: {arquivo} "
                        f"(referenciada por {tabela}.id={linha.id}). "
                        "Monte o volume de midia antes de aplicar a migration 0007 — "
                        "prosseguir apagaria o anexo do historico."
                    )
                conteudo = arquivo.read_bytes()
                extensao = arquivo.suffix.lower()
                novo_id = connection.execute(
                    sa.text(
                        "INSERT INTO media_objects "
                        "(tenant_id, media_type, content_type, extension, size_bytes, content) "
                        "VALUES (:tenant_id, :media_type, :content_type, :extension, "
                        ":size_bytes, :content) RETURNING id"
                    ),
                    {
                        "tenant_id": linha.tenant_id,
                        # A coluna guarda o NOME do membro do enum ("PHOTO"),
                        # que e como o SQLAlchemy persiste Enum nao-nativo — o
                        # valor minusculo aqui quebraria a leitura pelo ORM.
                        "media_type": linha.tipo or "PHOTO",
                        "content_type": CONTENT_TYPES.get(
                            extensao, "application/octet-stream"
                        ),
                        "extension": extensao or ".bin",
                        "size_bytes": len(conteudo),
                        "content": conteudo,
                    },
                ).scalar_one()
                ids_por_caminho[caminho] = novo_id

            connection.execute(
                sa.text(
                    f"UPDATE {tabela} SET {coluna_id} = :media_id WHERE id = :id"  # noqa: S608
                ),
                {"media_id": ids_por_caminho[caminho], "id": linha.id},
            )


def upgrade() -> None:
    op.create_table(
        "media_objects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("extension", sa.String(length=8), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_objects_tenant", "media_objects", ["tenant_id", "id"])
    op.create_index("ix_media_objects_tenant_id", "media_objects", ["tenant_id"])

    op.add_column("messages", sa.Column("media_id", sa.Integer(), nullable=True))
    op.create_index("ix_messages_media_id", "messages", ["media_id"])
    op.create_foreign_key(
        "fk_messages_media", "messages", "media_objects", ["media_id"], ["id"],
        ondelete="SET NULL",
    )

    op.add_column("funnel_contents", sa.Column("media_id", sa.Integer(), nullable=True))
    op.create_index("ix_funnel_contents_media_id", "funnel_contents", ["media_id"])
    op.create_foreign_key(
        "fk_funnel_contents_media", "funnel_contents", "media_objects", ["media_id"], ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "qualification_options", sa.Column("response_media_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_qualification_options_response_media_id",
        "qualification_options",
        ["response_media_id"],
    )
    op.create_foreign_key(
        "fk_qualification_options_media",
        "qualification_options",
        "media_objects",
        ["response_media_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _importar(op.get_bind())

    op.drop_column("messages", "media_path")
    op.drop_column("funnel_contents", "media_path")
    op.drop_column("qualification_options", "response_media_path")


def downgrade() -> None:
    """Volta as colunas de caminho, sem recriar os arquivos.

    A volta e estrutural: os bytes voltariam a precisar de um volume que a
    instalacao pode nao ter mais. Quem precisar reverter de verdade restaura o
    dump anterior — e por isso que a ida aborta em vez de perder arquivo.
    """
    op.add_column("qualification_options", sa.Column("response_media_path", sa.String(255)))
    op.add_column("funnel_contents", sa.Column("media_path", sa.String(255)))
    op.add_column("messages", sa.Column("media_path", sa.String(255)))

    op.drop_constraint("fk_qualification_options_media", "qualification_options")
    op.drop_index("ix_qualification_options_response_media_id", "qualification_options")
    op.drop_column("qualification_options", "response_media_id")

    op.drop_constraint("fk_funnel_contents_media", "funnel_contents")
    op.drop_index("ix_funnel_contents_media_id", "funnel_contents")
    op.drop_column("funnel_contents", "media_id")

    op.drop_constraint("fk_messages_media", "messages")
    op.drop_index("ix_messages_media_id", "messages")
    op.drop_column("messages", "media_id")

    op.drop_index("ix_media_objects_tenant_id", "media_objects")
    op.drop_index("ix_media_objects_tenant", "media_objects")
    op.drop_table("media_objects")
