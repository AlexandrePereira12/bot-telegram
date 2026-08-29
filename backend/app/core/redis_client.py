"""Cliente Redis compartilhado, rate limiting e locks.

Redis guarda apenas estado transitorio. Idempotencia definitiva mora no
PostgreSQL (tabela idempotency_keys) — ver planejamento/regras.md: dedup
deterministico no banco, nao mitigacao por TTL de cache.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis

from app.core.config import settings

_pool: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def rate_limit_hit(bucket: str, identifier: str, limit: int, window: int = 60) -> bool:
    """Contador por janela fixa. Retorna True quando o limite foi excedido.

    Se o Redis estiver indisponivel, nao bloqueia a requisicao (fail-open):
    derrubar login por indisponibilidade de cache seria pior que o risco.
    """
    key = f"rl:{settings.tenant_id}:{bucket}:{identifier}"
    try:
        client = get_redis()
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window)
        return current > limit
    except redis.RedisError:
        return False


@asynccontextmanager
async def distributed_lock(name: str, ttl: int = 30) -> AsyncIterator[bool]:
    """Lock simples por SET NX. Cede o controle indicando se obteve o lock."""
    key = f"lock:{settings.tenant_id}:{name}"
    client = get_redis()
    token = await client.set(key, "1", nx=True, ex=ttl)
    acquired = bool(token)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                await client.delete(key)
            except redis.RedisError:
                pass
