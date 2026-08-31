"""Teclados inline do bot."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.content_service import ResolvedOption


def consent_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Aceito os termos", callback_data="consent:accept")
    builder.button(text="Nao aceito", callback_data="consent:reject")
    builder.adjust(1)
    return builder.as_markup()


def age_keyboard(min_age: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Tenho {min_age} anos ou mais", callback_data="age:confirm")
    builder.button(text=f"Tenho menos de {min_age}", callback_data="age:reject")
    builder.adjust(1)
    return builder.as_markup()


def qualification_keyboard(options: list[ResolvedOption]) -> InlineKeyboardMarkup:
    """Opcoes vindas do painel (da campanha do lead ou globais)."""
    builder = InlineKeyboardBuilder()
    for option in options:
        builder.button(text=option.label, callback_data=f"interest:{option.key}")
    builder.adjust(1)
    return builder.as_markup()


def support_keyboard(options: list[ResolvedOption]) -> InlineKeyboardMarkup | None:
    """Atalho para atendimento humano, se a campanha oferecer essa opcao."""
    from app.core.enums import OptionTarget

    humano = next(
        (o for o in options if o.target == OptionTarget.HUMAN_SUPPORT), None
    )
    if humano is None:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text=humano.label, callback_data=f"interest:{humano.key}")
    return builder.as_markup()


def humano_keyboard() -> InlineKeyboardMarkup:
    """Saida para uma pessoa, presente em toda resposta da IA.

    Callback proprio (`humano:pedir`), e nao `interest:<key>`: o handler de
    qualificacao so aceita clique em QUALIFICATION ou INFORMATION, entao o
    botao seria descartado em silencio durante o atendimento — clique sem
    efeito e a pior versao de um caminho de escape.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Falar com uma pessoa", callback_data="humano:pedir")
    return builder.as_markup()
