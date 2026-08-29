"""Resolucao e ciclo de vida do tracking token (M10).

O token e opaco. Nenhum dado interno (campaign_id, source) trafega no
parametro do Telegram — o backend resolve.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import generate_tracking_token
from app.models import Campaign, TrackingToken

logger = get_logger(__name__)

ORGANIC_SOURCE = "organic"


@dataclass(frozen=True)
class Attribution:
    """Origem resolvida de uma entrada no funil."""

    campaign_id: int | None
    ad_set_id: int | None
    ad_id: int | None
    source: str
    token: str | None = None

    @property
    def is_attributed(self) -> bool:
        return self.campaign_id is not None


ORGANIC = Attribution(campaign_id=None, ad_set_id=None, ad_id=None, source=ORGANIC_SOURCE)


async def resolve_token(session: AsyncSession, raw_token: str | None) -> Attribution:
    """Resolve o token do deep link.

    Token ausente, desconhecido ou revogado cai em `organic` sem erro: o
    usuario chegou de verdade e o funil nao pode quebrar por causa da
    atribuicao (planejamento/ordens.md, aceite de M6 e M10).
    """
    if not raw_token:
        return ORGANIC

    token = raw_token.strip()
    if len(token) > 64:
        logger.warning("token de tracking com tamanho invalido descartado")
        return ORGANIC

    stmt = select(TrackingToken).where(
        TrackingToken.token == token,
        TrackingToken.tenant_id == settings.tenant_id,
    )
    found = (await session.execute(stmt)).scalar_one_or_none()

    if found is None:
        logger.info("token de tracking desconhecido; atribuindo organic")
        return ORGANIC
    if found.revoked_at is not None:
        logger.info("token de tracking revogado; atribuindo organic")
        return ORGANIC

    return Attribution(
        campaign_id=found.campaign_id,
        ad_set_id=found.ad_set_id,
        ad_id=found.ad_id,
        source=found.source,
        token=found.token,
    )


async def create_token(
    session: AsyncSession,
    *,
    campaign_id: int,
    ad_set_id: int | None = None,
    ad_id: int | None = None,
    source: str | None = None,
    label: str | None = None,
) -> TrackingToken:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != settings.tenant_id:
        raise ValueError("campanha inexistente")

    token = TrackingToken(
        tenant_id=settings.tenant_id,
        token=generate_tracking_token(),
        campaign_id=campaign_id,
        ad_set_id=ad_set_id,
        ad_id=ad_id,
        source=source or campaign.source,
        label=label,
    )
    session.add(token)
    await session.flush()
    return token


async def revoke_token(session: AsyncSession, token_id: int) -> TrackingToken:
    token = await session.get(TrackingToken, token_id)
    if token is None or token.tenant_id != settings.tenant_id:
        raise ValueError("token inexistente")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
    return token


def deep_link(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start={token}"
