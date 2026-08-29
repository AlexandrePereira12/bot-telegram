"""Enfileiramento de jobs (lado do produtor)."""

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue(job: str, **kwargs: Any) -> None:
    """Enfileira um job.

    Falha ao enfileirar nunca derruba a requisicao que chamou: o job e
    perdido e registrado, mas a API responde. Jobs criticos usam
    _job_id para dedup no proprio ARQ.
    """
    try:
        pool = await get_pool()
        await pool.enqueue_job(job, **kwargs)
    except Exception as exc:
        logger.error(
            "falha ao enfileirar job",
            extra={"event": "ENQUEUE_FAILED", "job": job, "error": type(exc).__name__},
        )
