"""Idempotencia deterministica por chave unica no PostgreSQL.

Regra (planejamento/regras.md): a verificacao acontece ANTES de qualquer
efeito colateral, na mesma transacao do efeito, e nunca depende so de TTL de
cache.
"""

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import IdempotencyKey


async def claim(session: AsyncSession, scope: str, key: str) -> bool:
    """Tenta reservar a chave.

    Retorna True se a chave e nova (o chamador deve executar o efeito) e
    False se ja foi processada antes (o chamador deve responder 200 sem
    reexecutar).
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""

    if dialect == "postgresql":
        stmt = (
            pg_insert(IdempotencyKey)
            .values(tenant_id=settings.tenant_id, scope=scope, key=key)
            .on_conflict_do_nothing(index_elements=["tenant_id", "scope", "key"])
            .returning(IdempotencyKey.id)
        )
        inserted = (await session.execute(stmt)).scalar_one_or_none()
        return inserted is not None

    # SQLite (testes): mesma semantica via constraint unica + savepoint.
    try:
        async with session.begin_nested():
            session.add(
                IdempotencyKey(tenant_id=settings.tenant_id, scope=scope, key=key)
            )
        return True
    except IntegrityError:
        return False
