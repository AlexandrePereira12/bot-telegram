"""Conteudo do funil editavel pelo painel.

Cada campanha pode ter sua propria conversa. Linha com `campaign_id` nulo e o
padrao global, usado por qualquer campanha que nao tenha versao propria.
"""

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import FunnelStep, MediaType, OptionTarget
from app.models.base import TenantMixin, TimestampMixin, UpdatedAtMixin


class FunnelContent(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "funnel_contents"
    __table_args__ = (
        # postgresql_nulls_not_distinct faz o Postgres tratar campaign_id NULL
        # como valor unico: sem isso daria para criar varias linhas globais
        # para a mesma etapa e a resolucao viraria loteria.
        UniqueConstraint(
            "tenant_id",
            "campaign_id",
            "step",
            name="uq_funnel_contents_tenant_campaign_step",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_funnel_contents_lookup", "tenant_id", "campaign_id", "step"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: NULL = padrao global.
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[FunnelStep] = mapped_column(
        Enum(FunnelStep, native_enum=False, length=32), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Caminho relativo dentro do volume de midia — nunca uma URL: o servidor
    #: do Telegram nao alcanca o host local, entao o arquivo e enviado como
    #: bytes a partir do disco.
    media_path: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[MediaType | None] = mapped_column(
        Enum(MediaType, native_enum=False, length=16)
    )


class QualificationOption(Base, TenantMixin, TimestampMixin, UpdatedAtMixin):
    """Botao da etapa de qualificacao."""

    __tablename__ = "qualification_options"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "campaign_id",
            "key",
            name="uq_qualification_options_tenant_campaign_key",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_qualification_options_lookup", "tenant_id", "campaign_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: NULL = conjunto global de opcoes.
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    #: Identificador gravado em `leads.interest` e no metadata dos eventos.
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[OptionTarget] = mapped_column(
        Enum(OptionTarget, native_enum=False, length=16),
        nullable=False,
        default=OptionTarget.INFORMATION,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Desativar em vez de apagar: `leads.interest` e os eventos ja gravados
    #: referenciam a key, e removê-la deixaria buraco no historico.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: Resposta propria desta opcao. Vazio faz o bot cair na mensagem generica
    #: da etapa INFORMATION, que e o comportamento anterior.
    #: So se aplica a opcao com target=INFORMATION: quem vai para atendimento
    #: humano recebe a mensagem de fila, nao um texto de conteudo.
    response_body: Mapped[str | None] = mapped_column(Text)
    response_media_path: Mapped[str | None] = mapped_column(String(255))
    response_media_type: Mapped[MediaType | None] = mapped_column(
        Enum(MediaType, native_enum=False, length=16)
    )
