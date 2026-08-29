"""Registro dos routers de handler."""

from aiogram import Router

from app.bot.handlers import commands, funnel, messages


def build_router() -> Router:
    router = Router(name="root")
    # Ordem importa: comandos antes do catch-all de mensagem livre.
    router.include_router(commands.router)
    router.include_router(funnel.router)
    router.include_router(messages.router)
    return router
