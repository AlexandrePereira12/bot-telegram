"""Resolucao do conteudo do funil.

Ordem de busca, sempre: conteudo da campanha do lead -> conteudo global ->
texto fixo em `app.bot.texts`. O terceiro nivel nao e redundancia: se alguem
apagar a linha global, o bot precisa continuar respondendo.
"""

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.core.config import settings
from app.core.enums import GLOBAL_ONLY_STEPS, FunnelStep, MediaType, OptionTarget
from app.core.logging import get_logger
from app.models import FunnelContent, QualificationOption

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedContent:
    body: str
    #: Referencia em `media_objects`; os bytes sao lidos na hora do envio.
    media_id: int | None = None
    media_type: MediaType | None = None


@dataclass(frozen=True)
class ResolvedOption:
    key: str
    label: str
    target: OptionTarget
    #: Resposta propria da opcao; None faz cair no texto generico da etapa.
    response_body: str | None = None
    response_media_id: int | None = None
    response_media_type: MediaType | None = None

    def response(self) -> ResolvedContent | None:
        if not self.response_body:
            return None
        return ResolvedContent(
            body=self.response_body,
            media_id=self.response_media_id,
            media_type=self.response_media_type,
        )


def _fallback(step: FunnelStep) -> str:
    """Texto do codigo, ultimo recurso quando o banco nao tem a etapa."""
    mapping = {
        FunnelStep.WELCOME: texts.WELCOME,
        FunnelStep.CONSENT: texts.CONSENT,
        FunnelStep.CONSENT_REQUIRED: texts.CONSENT_REQUIRED,
        FunnelStep.AGE_GATE: texts.AGE_GATE,
        FunnelStep.AGE_REJECTED: texts.AGE_REJECTED,
        FunnelStep.QUALIFICATION: texts.QUALIFICATION,
        FunnelStep.INFORMATION: texts.INFORMATION,
        FunnelStep.AI_SUPPORT: texts.AI_SUPPORT,
        FunnelStep.HUMAN_SUPPORT: texts.HUMAN_SUPPORT,
        FunnelStep.FOLLOWUP: texts.FOLLOWUP,
    }
    return mapping[step]


def render(body: str, **extra: object) -> str:
    """Aplica as variaveis disponiveis ao corpo.

    Placeholder desconhecido no texto (digitado errado no painel) nao pode
    derrubar o envio: mantem o texto como esta e segue.
    """
    values: dict[str, object] = {
        "company": settings.company_name,
        "min_age": settings.min_age,
        "version": settings.consent_version,
        "name": "",
        "interest": "",
        **extra,
    }
    try:
        return body.format(**values)
    except (KeyError, IndexError, ValueError):
        logger.warning(
            "placeholder invalido no conteudo do funil",
            extra={"event": "CONTENT_RENDER_FAILED"},
        )
        return body


async def get_content(
    session: AsyncSession, step: FunnelStep, campaign_id: int | None
) -> ResolvedContent:
    """Conteudo da etapa para a campanha informada."""
    # Etapa de efeito legal ignora o override por campanha.
    lookup_campaign = None if step in GLOBAL_ONLY_STEPS else campaign_id

    # `campaign_id IN (:id, NULL)` nunca casaria com a linha global: em SQL,
    # comparar com NULL resulta em desconhecido, nao em verdadeiro. Por isso o
    # OR explicito com IS NULL.
    escopo = (
        or_(FunnelContent.campaign_id == lookup_campaign, FunnelContent.campaign_id.is_(None))
        if lookup_campaign is not None
        else FunnelContent.campaign_id.is_(None)
    )
    stmt = select(FunnelContent).where(
        FunnelContent.tenant_id == settings.tenant_id,
        FunnelContent.step == step,
        escopo,
    )
    rows = list((await session.execute(stmt)).scalars())

    # Campanha vence global quando as duas existem.
    chosen = next((r for r in rows if r.campaign_id == lookup_campaign), None) or next(
        (r for r in rows if r.campaign_id is None), None
    )

    if chosen is None:
        return ResolvedContent(body=_fallback(step))
    return ResolvedContent(
        body=chosen.body, media_id=chosen.media_id, media_type=chosen.media_type
    )


async def get_options(
    session: AsyncSession, campaign_id: int | None
) -> list[ResolvedOption]:
    """Opcoes de qualificacao ativas, da campanha ou globais."""
    # Mesmo cuidado do get_content: IN com NULL nao casa com a linha global.
    escopo = (
        or_(
            QualificationOption.campaign_id == campaign_id,
            QualificationOption.campaign_id.is_(None),
        )
        if campaign_id is not None
        else QualificationOption.campaign_id.is_(None)
    )
    stmt = (
        select(QualificationOption)
        .where(
            QualificationOption.tenant_id == settings.tenant_id,
            QualificationOption.is_active.is_(True),
            escopo,
        )
        .order_by(QualificationOption.sort_order, QualificationOption.id)
    )
    rows = list((await session.execute(stmt)).scalars())

    # Conjunto proprio da campanha substitui o global inteiro — nao mistura,
    # senao a ordem e o total ficariam imprevisiveis.
    own = [r for r in rows if r.campaign_id == campaign_id and campaign_id is not None]
    chosen = own or [r for r in rows if r.campaign_id is None]

    if not chosen:
        return [
            ResolvedOption(
                key=key,
                label=label,
                target=OptionTarget.HUMAN_SUPPORT
                if key == "human_support"
                else OptionTarget.INFORMATION,
            )
            for label, key in texts.INTERESTS.items()
        ]
    return [
        ResolvedOption(
            key=r.key,
            label=r.label,
            target=r.target,
            response_body=r.response_body,
            response_media_id=r.response_media_id,
            response_media_type=r.response_media_type,
        )
        for r in chosen
    ]


async def resolve_option(
    session: AsyncSession, campaign_id: int | None, key: str
) -> ResolvedOption | None:
    """Opcao escolhida pelo lead, ou None se nao existir/estiver inativa."""
    for option in await get_options(session, campaign_id):
        if option.key == key:
            return option
    return None
