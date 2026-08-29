"""Middlewares do aiogram: sessao de banco e rate limit por usuario."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.core.redis_client import rate_limit_hit

logger = get_logger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Injeta uma AsyncSession por update e commita ao final.

    Uma transacao por update mantem a FSM consistente: ou o estado avanca e o
    evento e gravado juntos, ou nada e gravado.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with SessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class RateLimitMiddleware(BaseMiddleware):
    """Limita updates por usuario do Telegram.

    Update descartado silenciosamente: responder "voce excedeu o limite" a
    cada mensagem so amplifica o flood.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = self._extract_user_id(event)
        if user_id is not None:
            exceeded = await rate_limit_hit(
                "telegram", str(user_id), settings.rate_limit_telegram_per_minute
            )
            if exceeded:
                logger.warning(
                    "update descartado por rate limit",
                    extra={"event": "TELEGRAM_RATE_LIMITED", "user_id": user_id},
                )
                return None
        return await handler(event, data)

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Update):
            if event.message and event.message.from_user:
                return event.message.from_user.id
            if event.callback_query and event.callback_query.from_user:
                return event.callback_query.from_user.id
        from_user = getattr(event, "from_user", None)
        return from_user.id if from_user else None


class ErrorLoggingMiddleware(BaseMiddleware):
    """Erro em um update nunca derruba o processo do bot."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception(
                "erro ao processar update",
                extra={"event": "BOT_HANDLER_ERROR", "error": type(exc).__name__},
            )
            return None
