"""Aplicacao FastAPI: API REST, webhooks e control plane."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    analytics,
    auth,
    campaigns,
    content,
    conversations,
    health,
    leads,
    operators,
    webhooks,
)
from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.redis_client import close_redis

logger = get_logger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging("api")
    settings.validate_runtime()

    app.state.bot = None
    app.state.dispatcher = None
    app.state.bot_username = None

    if settings.telegram_bot_token:
        from app.bot.bot import configure_webhook, create_bot, create_dispatcher, resolve_username

        bot = create_bot()
        app.state.bot = bot
        app.state.bot_username = await resolve_username(bot)

        if settings.telegram_use_webhook:
            # Em producao a API e quem recebe os updates.
            app.state.dispatcher = create_dispatcher()
            try:
                await configure_webhook(bot)
            except Exception as exc:
                logger.error(
                    "falha ao configurar webhook do telegram",
                    extra={"event": "WEBHOOK_SETUP_FAILED", "error": type(exc).__name__},
                )

    logger.info(
        "api iniciada",
        extra={"event": "API_STARTED", "environment": settings.app_env},
    )
    try:
        yield
    finally:
        if app.state.bot is not None:
            await app.state.bot.session.close()
        await close_redis()
        await engine.dispose()


app = FastAPI(
    title=f"Traffic Bot API — {settings.company_name}",
    version="0.1.0",
    lifespan=lifespan,
    # Documentacao interativa fica fora do ar em producao.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Erro inesperado nunca vaza stack trace nem detalhe interno."""
    logger.exception(
        "erro nao tratado",
        extra={"event": "UNHANDLED_ERROR", "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "erro interno"},
    )


app.include_router(health.router)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(campaigns.router, prefix=API_PREFIX)
app.include_router(content.router, prefix=API_PREFIX)
app.include_router(leads.router, prefix=API_PREFIX)
app.include_router(conversations.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(operators.router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"company": settings.company_name, "status": "ok"}
