"""Callbacks do funil: consentimento, age gate e qualificacao."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import age_keyboard, qualification_keyboard, support_keyboard
from app.core.config import settings
from app.core.enums import (
    FunnelState,
    FunnelStep,
    MessageDirection,
    OptionTarget,
    SenderType,
)
from app.core.logging import get_logger
from app.models import Lead, TelegramUser
from app.services import content_service, conversation_service, funnel_service, lead_service
from app.services.content_service import ResolvedContent

router = Router(name="funnel")
logger = get_logger(__name__)


async def _content(
    session: AsyncSession, step: FunnelStep, lead: Lead | None, **extra: object
) -> ResolvedContent:
    campaign_id = lead.last_touch_campaign_id if lead else None
    resolved = await content_service.get_content(session, step, campaign_id)
    return ResolvedContent(
        body=content_service.render(resolved.body, **extra),
        media_id=resolved.media_id,
        media_type=resolved.media_type,
    )


async def _answer(
    callback: CallbackQuery,
    session: AsyncSession,
    user: TelegramUser,
    content: ResolvedContent | str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Responde ao callback e registra a saida do bot."""
    if callback.message is not None:
        from app.bot.replies import send

        await send(callback.message, content, session=session, user=user, markup=markup)
    await callback.answer()


async def _load(callback: CallbackQuery, session: AsyncSession):
    user, _ = await lead_service.get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    lead = await lead_service.get_lead_by_user(session, user.id)
    return user, lead


@router.callback_query(F.data == "consent:accept")
async def on_consent_accept(callback: CallbackQuery, session: AsyncSession) -> None:
    user, lead = await _load(callback, session)
    if user.is_blocked:
        await callback.answer()
        return
    if FunnelState(user.current_state) != FunnelState.CONSENT:
        # Botao antigo reclicado: nao reprocessa nem regride o estado.
        await callback.answer()
        return

    await funnel_service.accept_consent(session, user, lead)
    await _answer(
        callback,
        session,
        user,
        await _content(session, FunnelStep.AGE_GATE, lead),
        markup=age_keyboard(settings.min_age),
    )


@router.callback_query(F.data == "consent:reject")
async def on_consent_reject(callback: CallbackQuery, session: AsyncSession) -> None:
    user, lead = await _load(callback, session)
    if FunnelState(user.current_state) != FunnelState.CONSENT:
        await callback.answer()
        return
    await funnel_service.reject_consent(session, user, lead)
    await _answer(
        callback, session, user, await _content(session, FunnelStep.CONSENT_REQUIRED, lead)
    )


@router.callback_query(F.data == "age:confirm")
async def on_age_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    user, lead = await _load(callback, session)
    if user.age_rejected:
        # Reprovado no age gate nao reentra por reclicar o botao.
        await _answer(
            callback, session, user, await _content(session, FunnelStep.AGE_REJECTED, lead)
        )
        return
    if FunnelState(user.current_state) != FunnelState.AGE_GATE:
        await callback.answer()
        return

    await funnel_service.confirm_age(session, user, lead)
    campaign_id = lead.last_touch_campaign_id if lead else None
    options = await content_service.get_options(session, campaign_id)
    await _answer(
        callback,
        session,
        user,
        await _content(session, FunnelStep.QUALIFICATION, lead),
        markup=qualification_keyboard(options),
    )


@router.callback_query(F.data == "age:reject")
async def on_age_reject(callback: CallbackQuery, session: AsyncSession) -> None:
    user, lead = await _load(callback, session)
    if FunnelState(user.current_state) not in (FunnelState.AGE_GATE, FunnelState.EXIT):
        await callback.answer()
        return
    await funnel_service.reject_age(session, user, lead)
    await _answer(
        callback, session, user, await _content(session, FunnelStep.AGE_REJECTED, lead)
    )


@router.callback_query(F.data.startswith("interest:"))
async def on_interest(callback: CallbackQuery, session: AsyncSession) -> None:
    user, lead = await _load(callback, session)
    key = (callback.data or "").split(":", 1)[1]
    campaign_id = lead.last_touch_campaign_id if lead else None

    # A opcao precisa existir e estar ativa para esta campanha — callback
    # forjado ou botao de uma opcao ja desativada nao muda estado.
    option = await content_service.resolve_option(session, campaign_id, key)
    if option is None:
        await callback.answer()
        return

    state = FunnelState(user.current_state)
    if state not in (FunnelState.QUALIFICATION, FunnelState.INFORMATION):
        await callback.answer()
        return

    target = await funnel_service.select_interest(session, user, lead, option)

    if target == OptionTarget.HUMAN_SUPPORT:
        await _answer(
            callback, session, user, await _content(session, FunnelStep.HUMAN_SUPPORT, lead)
        )
    else:
        options = await content_service.get_options(session, campaign_id)
        # Resposta propria da opcao escolhida; sem ela, cai na mensagem
        # generica da etapa INFORMATION.
        propria = option.response()
        if propria is not None:
            resposta = ResolvedContent(
                body=content_service.render(propria.body, interest=option.label),
                media_id=propria.media_id,
                media_type=propria.media_type,
            )
        else:
            resposta = await _content(
                session, FunnelStep.INFORMATION, lead, interest=option.label
            )
        await _answer(callback, session, user, resposta, markup=support_keyboard(options))


__all__ = ["router", "conversation_service", "MessageDirection", "SenderType"]
