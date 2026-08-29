"""Construcao do bot aiogram e dos dois modos de operacao.

Modo de execucao (decisao registrada em planejamento/como-usar.md):

- desenvolvimento: TELEGRAM_USE_WEBHOOK=false -> o servico `bot` roda em
  long polling. Nao exige HTTPS publico, funciona na maquina do dev.
- producao: TELEGRAM_USE_WEBHOOK=true -> a API recebe os updates em
  /api/v1/webhooks/telegram, autenticados por secret_token.

Os dois modos usam o mesmo Dispatcher e os mesmos handlers.
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import build_router
from app.bot.middlewares import DatabaseMiddleware, ErrorLoggingMiddleware, RateLimitMiddleware
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


def create_dispatcher() -> Dispatcher:
    """Dispatcher com os middlewares na ordem correta.

    O storage em memoria do aiogram guarda apenas contexto efemero de UI. O
    estado do funil vive em telegram_users.current_state, no banco: reiniciar
    o processo nao perde progresso (M7).
    """
    dispatcher = Dispatcher(storage=MemoryStorage())

    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.middleware(ErrorLoggingMiddleware())
        observer.middleware(RateLimitMiddleware())
        observer.middleware(DatabaseMiddleware())

    dispatcher.include_router(build_router())
    return dispatcher


async def resolve_username(bot: Bot) -> str | None:
    try:
        me = await bot.get_me()
        return me.username
    except Exception as exc:
        logger.warning(
            "nao foi possivel consultar o bot no Telegram",
            extra={"event": "TELEGRAM_UNAVAILABLE", "error": type(exc).__name__},
        )
        return None


async def configure_webhook(bot: Bot) -> None:
    url = f"https://{settings.api_domain}/api/v1/webhooks/telegram"
    await bot.set_webhook(
        url=url,
        secret_token=settings.telegram_webhook_secret,
        drop_pending_updates=False,
        allowed_updates=["message", "callback_query"],
    )
    logger.info("webhook do telegram configurado", extra={"event": "WEBHOOK_CONFIGURED"})


async def run_polling() -> None:
    """Entrypoint do servico `bot` em desenvolvimento."""
    from app.core.logging import setup_logging

    setup_logging("bot")
    settings.validate_runtime("bot")

    bot = create_bot()
    dispatcher = create_dispatcher()

    # A sessao HTTP e fechada em qualquer saida, inclusive falha de
    # autenticacao na primeira chamada — senao o aiohttp reclama de
    # "Unclosed client session" e polui o log do erro que importa.
    try:
        # Garante que nao ha webhook ativo competindo com o polling.
        await bot.delete_webhook(drop_pending_updates=False)
        username = await resolve_username(bot)
        logger.info(
            "bot iniciado em polling",
            extra={"event": "BOT_STARTED", "bot_username": username},
        )
        await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
    except TelegramUnauthorizedError:
        # Causa quase sempre e token errado/revogado. Mensagem direta vale
        # mais que o stacktrace do aiogram, ainda mais em restart loop.
        logger.error(
            "Telegram recusou o token: confira TELEGRAM_BOT_TOKEN no .env "
            "(valor do BotFather, formato 123456789:AA...).",
            extra={"event": "TELEGRAM_UNAUTHORIZED"},
        )
        raise SystemExit(1) from None
    finally:
        await bot.session.close()


def main() -> None:
    import asyncio

    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
