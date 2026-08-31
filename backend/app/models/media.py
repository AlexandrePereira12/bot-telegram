"""Arquivo de midia guardado no banco.

Imagem, video e audio vivem aqui como bytes, e nao num volume do host. A
razao e operacional: o backup do PostgreSQL passa a ser o backup completo do
atendimento. Com o arquivo fora do banco, restaurar so o dump devolvia linhas
apontando para arquivo inexistente — conversa com buraco, sem erro nenhum no
caminho.

O teto por arquivo e `MAX_MEDIA_MB` (20MB, o mesmo do Telegram). Nessa faixa
o TOAST do Postgres guarda o conteudo fora da linha e comprime sozinho, entao
`bytea` resolve sem a complicacao de large object (`lo_*`, `vacuumlo`) e sem
sair do `pg_dump` comum.
"""

from sqlalchemy import Enum, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import MediaType
from app.models.base import TenantMixin, TimestampMixin


class MediaObject(Base, TenantMixin, TimestampMixin):
    __tablename__ = "media_objects"
    __table_args__ = (Index("ix_media_objects_tenant", "tenant_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=16), nullable=False
    )
    #: MIME devolvido ao painel. Guardado no registro em vez de deduzido do
    #: nome do arquivo, que deixou de existir.
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Extensao usada no nome que vai ao Telegram: `sendVoice` e `sendAudio`
    #: decidem o tipo pelo nome, e um `.ogg` chamado de `.bin` chega errado.
    extension: Mapped[str] = mapped_column(String(8), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    def filename(self) -> str:
        return f"midia-{self.id}{self.extension}"
