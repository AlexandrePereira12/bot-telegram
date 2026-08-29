"""Fixtures dos testes.

Banco SQLite em memoria: rapido e sem dependencia externa. Os pontos em que
o dialeto muda o comportamento (JSONB, ON CONFLICT) tem caminho explicito no
codigo de producao e sao exercitados aqui pela mesma constraint unica.
"""

import os

os.environ.setdefault("COMPANY_SLUG", "empresa-teste")
os.environ.setdefault("COMPANY_NAME", "Empresa Teste")
os.environ.setdefault("JWT_SECRET", "test-secret-nao-usar-em-producao")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("CONVERSION_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("MEDIA_ROOT", "/tmp/traffic-bot-test-media")

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.database import Base


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        yield db

    await engine.dispose()


@pytest_asyncio.fixture
async def campaign(session: AsyncSession):
    from app.core.config import settings
    from app.models import Campaign

    item = Campaign(
        tenant_id=settings.tenant_id,
        name="Campanha teste",
        source="meta",
        platform="meta_ads",
        external_id="test-001",
    )
    session.add(item)
    await session.flush()
    return item


@pytest_asyncio.fixture
async def global_content(session: AsyncSession):
    """Semeia o conteudo global, como faz a migration 0003."""
    from app.core.config import settings
    from app.core.enums import FunnelStep, OptionTarget
    from app.models import FunnelContent, QualificationOption

    textos = {
        FunnelStep.WELCOME: "Ola{name}! Bem-vindo(a) a {company}.",
        FunnelStep.CONSENT: "Termos versao {version}. Voce aceita?",
        FunnelStep.CONSENT_REQUIRED: "Sem aceite nao seguimos.",
        FunnelStep.AGE_GATE: "Restrito a maiores de {min_age}. Confirma?",
        FunnelStep.AGE_REJECTED: "Restrito a maiores de {min_age}.",
        FunnelStep.QUALIFICATION: "O que voce procura?",
        FunnelStep.INFORMATION: "Informacoes sobre {interest}.",
        FunnelStep.HUMAN_SUPPORT: "Voce entrou na fila de atendimento.",
        FunnelStep.FOLLOWUP: "Voce nao concluiu. Quer continuar?",
    }
    for step, body in textos.items():
        session.add(
            FunnelContent(tenant_id=settings.tenant_id, campaign_id=None, step=step, body=body)
        )
    for i, (key, label, target) in enumerate(
        [
            ("service_info", "Conhecer o servico", OptionTarget.INFORMATION),
            ("faq", "Tirar duvidas", OptionTarget.INFORMATION),
            ("human_support", "Falar com atendente", OptionTarget.HUMAN_SUPPORT),
        ]
    ):
        session.add(
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=None,
                key=key,
                label=label,
                target=target,
                sort_order=i * 10,
            )
        )
    await session.flush()
