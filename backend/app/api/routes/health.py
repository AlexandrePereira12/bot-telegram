"""Health check, readiness e metricas Prometheus."""

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.schemas import ComponentHealth, HealthResponse

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, session: SessionDep) -> HealthResponse:
    """Status componente a componente.

    Nunca expoe host, credencial ou string de conexao — so o estado.
    """
    components: dict[str, ComponentHealth] = {"api": ComponentHealth(status="ok")}

    try:
        await session.execute(text("SELECT 1"))
        components["postgres"] = ComponentHealth(status="ok")
    except Exception as exc:
        logger.error("health: postgres indisponivel", extra={"error": type(exc).__name__})
        components["postgres"] = ComponentHealth(status="error", detail="indisponivel")

    try:
        await get_redis().ping()
        components["redis"] = ComponentHealth(status="ok")
    except Exception as exc:
        logger.error("health: redis indisponivel", extra={"error": type(exc).__name__})
        components["redis"] = ComponentHealth(status="error", detail="indisponivel")

    bot_username = getattr(request.app.state, "bot_username", None)
    components["telegram"] = (
        ComponentHealth(status="ok", detail=f"@{bot_username}")
        if bot_username
        else ComponentHealth(status="disabled", detail="token nao configurado")
    )

    try:
        redis = get_redis()
        # ARQ mantem a lista de workers ativos nesta chave.
        workers = await redis.zcard("arq:queue:health")
        pending = await redis.llen("arq:queue")
        components["workers"] = ComponentHealth(
            status="ok", detail=f"fila com {pending} job(s) pendente(s)"
        ) if workers is not None else ComponentHealth(status="error")
    except Exception:
        components["workers"] = ComponentHealth(status="error", detail="fila indisponivel")

    degraded = any(c.status == "error" for c in components.values())
    return HealthResponse(
        status="degraded" if degraded else "ok",
        company=settings.company_slug,
        environment=settings.app_env,
        components=components,
    )


@router.get("/ready")
async def ready(session: SessionDep) -> dict[str, str]:
    """Readiness: so responde ok se o banco aceitar query."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
