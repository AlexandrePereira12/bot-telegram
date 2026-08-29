"""Comandos do bot: /start, /status, /parar, /ajuda."""

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import age_keyboard, consent_keyboard, qualification_keyboard
from app.bot.replies import send
from app.core.config import settings
from app.core.enums import EventType, FunnelState, FunnelStep
from app.core.logging import get_logger
from app.models import Lead, TelegramUser
from app.services import content_service, funnel_service, lead_service, tracking_service
from app.services.event_service import record_event

router = Router(name="commands")
logger = get_logger(__name__)


async def _content(
    session: AsyncSession, step: FunnelStep, lead: Lead | None, **extra: object
):
    """Conteudo da etapa para a campanha do lead, ja renderizado."""
    campaign_id = lead.last_touch_campaign_id if lead else None
    resolved = await content_service.get_content(session, step, campaign_id)
    return content_service.ResolvedContent(
        body=content_service.render(resolved.body, **extra),
        media_path=resolved.media_path,
        media_type=resolved.media_type,
    )


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session: AsyncSession) -> None:
    """Entrada do funil (CU1).

    Resolve o token de rastreamento, cria/atualiza usuario e lead, registra
    USER_STARTED e leva ao proximo passo pendente. Token invalido ou revogado
    cai em `organic` sem quebrar o fluxo.
    """
    if message.from_user is None:
        return

    attribution = await tracking_service.resolve_token(session, command.args)

    user, _ = await lead_service.get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        language=message.from_user.language_code,
    )

    if user.is_blocked:
        await send(message, texts.BLOCKED, session=session, user=user)
        return

    lead, _ = await lead_service.get_or_create_lead(session, user, attribution)

    await record_event(
        session,
        EventType.USER_STARTED,
        telegram_user_id=user.id,
        lead_id=lead.id,
        campaign_id=attribution.campaign_id,
        metadata={
            "source": attribution.source,
            "attributed": attribution.is_attributed,
            "ad_id": attribution.ad_id,
        },
    )

    await resume_funnel(message, session, user, lead)


async def _send_qualification(
    message: Message, session: AsyncSession, user: TelegramUser, lead: Lead | None
) -> None:
    campaign_id = lead.last_touch_campaign_id if lead else None
    options = await content_service.get_options(session, campaign_id)
    await send(
        message,
        await _content(session, FunnelStep.QUALIFICATION, lead),
        session=session,
        user=user,
        markup=qualification_keyboard(options),
    )


async def resume_funnel(
    message: Message, session: AsyncSession, user: TelegramUser, lead: Lead | None
) -> None:
    """Leva o usuario ao proximo passo pendente do funil.

    Reentrada e sempre retomada, nunca reinicio: quem ja foi reprovado no age
    gate ou ja converteu nao volta ao inicio (regra de compliance).
    """
    state = FunnelState(user.current_state)

    if user.age_rejected:
        await send(
            message,
            await _content(session, FunnelStep.AGE_REJECTED, lead),
            session=session,
            user=user,
        )
        return

    if state == FunnelState.CONVERTED:
        # CONVERTED so e alcancado quando um ciclo fecha, entao mensagem nova
        # aqui significa que o lead voltou: comeca um atendimento novo em vez
        # de responder que ele ja esta na fila. O historico do ciclo anterior
        # (conversao, atribuicao) permanece.
        await funnel_service.reopen(session, user, lead)
        await _send_qualification(message, session, user, lead)
        return

    if state == FunnelState.EXIT:
        # Saida por desistencia: retoma do ponto ja alcancado, sem repetir
        # consentimento nem age gate ja respondidos.
        state = await funnel_service.restart_from_exit(session, user, lead)
        if state == FunnelState.QUALIFICATION:
            await _send_qualification(message, session, user, lead)
            return
        if state == FunnelState.AGE_GATE:
            await send(
                message,
                await _content(session, FunnelStep.AGE_GATE, lead),
                session=session,
                user=user,
                markup=age_keyboard(settings.min_age),
            )
            return

    if state in (FunnelState.NEW, FunnelState.WELCOME):
        await funnel_service.transition(
            session, user, FunnelState.WELCOME, lead=lead, event=EventType.WELCOME_SENT
        )
        await send(
            message,
            await _content(session, FunnelStep.WELCOME, lead, name=user.first_name or ""),
            session=session,
            user=user,
        )
        await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
        await record_event(
            session,
            EventType.CONSENT_VIEWED,
            telegram_user_id=user.id,
            lead_id=lead.id if lead else None,
        )
        await send(
            message,
            await _content(session, FunnelStep.CONSENT, lead),
            session=session,
            user=user,
            markup=consent_keyboard(),
        )
        return

    if state == FunnelState.CONSENT:
        await record_event(
            session,
            EventType.CONSENT_VIEWED,
            telegram_user_id=user.id,
            lead_id=lead.id if lead else None,
        )
        await send(
            message,
            await _content(session, FunnelStep.CONSENT, lead),
            session=session,
            user=user,
            markup=consent_keyboard(),
        )
        return

    if state == FunnelState.AGE_GATE:
        await send(
            message,
            await _content(session, FunnelStep.AGE_GATE, lead),
            session=session,
            user=user,
            markup=age_keyboard(settings.min_age),
        )
        return

    if state == FunnelState.HUMAN_SUPPORT:
        await send(
            message,
            await _content(session, FunnelStep.HUMAN_SUPPORT, lead),
            session=session,
            user=user,
        )
        return

    # QUALIFICATION ou INFORMATION: reapresenta as opcoes.
    await _send_qualification(message, session, user, lead)


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
    )
    await send(
        message,
        f"Etapa atual: {user.current_state.value}",
        session=session,
        user=user,
    )


@router.message(Command("parar"))
async def cmd_stop(message: Message, session: AsyncSession) -> None:
    """Revogacao de consentimento pelo proprio usuario (CU6)."""
    if message.from_user is None:
        return
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
    )
    await funnel_service.revoke_consent(session, user)
    await send(message, texts.CONSENT_REVOKED, session=session, user=user)


@router.message(Command("ajuda"))
async def cmd_help(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
    )
    await send(message, texts.HELP, session=session, user=user)


__all__ = ["router", "resume_funnel"]
