"""Engine e sessao do SQLAlchemy (async)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _engine_options() -> dict:
    """Opcoes de pool so se aplicam a bancos em rede.

    SQLite (usado nos testes) usa StaticPool e rejeita pool_size/max_overflow.
    """
    if settings.database_url.startswith("sqlite"):
        return {}
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine = create_async_engine(settings.database_url, echo=False, **_engine_options())

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI. Commit explicito fica a cargo do service."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
