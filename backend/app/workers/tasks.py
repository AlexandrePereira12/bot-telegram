"""Jobs assincronos (M18, M19).

Regras aplicadas em todo job:
- consentimento vigente e verificado ANTES de qualquer envio de marketing;
- efeito com chave de idempotencia deterministica no banco;
- ate 3 tentativas; esgotadas, o job vai para a fila de erro (dead-letter)
  em vez de sumir silenciosamente.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from arq import Retry
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.enums import EventType, FunnelState, MediaType, MessageDirection, SenderType
from app.core.logging import get_logger, setup_logging
from app.models import Lead, TelegramUser
from app.services import conversation_service, funnel_service
from app.services.event_service import record_event
from app.services.idempotency_service import claim
from app.workers.queue import redis_settings

logger = get_logger(__name__)

MAX_TRIES = 3
DEAD_LETTER_KEY = "arq:dead-letter"


async def _to_dead_letter(ctx: dict[str, Any], job: str, reason: str, payload: dict) -> None:
    """Ultimo recurso: preserva o job falho para inspecao manual."""
    import json

    try:
        await ctx["redis"].rpush(
            DEAD_LETTER_KEY,
            json.dumps(
                {
                    "tenant_id": settings.tenant_id,
                    "job": job,
                    "reason": reason,
                    "payload": payload,
                    "at": datetime.now(UTC).isoformat(),
                }
            ),
        )
    except Exception:
        logger.exception("falha ao gravar dead-letter", extra={"event": "DEADLETTER_FAILED"})


async def _fallback_texto(bot: Any, telegram_id: int, text: str, tinha_midia: bool) -> None:
    """Envia o texto quando a midia nao pode sair.

    Mensagem que era so anexo fica sem texto nenhum: mandar string vazia seria
    erro da API do Telegram, entao o envio simplesmente nao acontece e o
    problema fica no log em vez de virar retry infinito.
    """
    if text and text.strip():
        await bot.send_message(chat_id=telegram_id, text=text)
        return
    logger.warning(
        "mensagem sem texto e sem midia utilizavel; nada enviado",
        extra={"event": "MESSAGE_DROPPED", "tinha_midia": tinha_midia},
    )


async def send_telegram_message(
    ctx: dict[str, Any],
    telegram_id: int,
    text: str,
    message_id: int | None = None,
    media_id: int | None = None,
) -> dict[str, Any]:
    """Envia mensagem pelo Telegram fora do ciclo de request da API.

    Com midia, os bytes vem de `media_objects` e sobem como upload — o
    servidor do Telegram nao alcancaria uma URL local, e nao existe mais
    arquivo em disco para apontar.

    Cada tipo tem seu metodo: voz precisa de `send_voice` para virar bolha de
    audio gravado, e tipo desconhecido cai para texto em vez de ser mandado
    pelo metodo errado.
    """
    from aiogram.types import BufferedInputFile

    from app.bot.bot import create_bot
    from app.services import media_service

    media = None
    if media_id is not None:
        async with SessionLocal() as session:
            media = await media_service.load(session, media_id)
        if media is None:
            logger.warning(
                "midia da mensagem nao encontrada; enviando so o texto",
                extra={"event": "MEDIA_NOT_FOUND", "media_id": media_id},
            )

    bot = create_bot()
    try:
        if media is not None:
            arquivo = BufferedInputFile(media.content, filename=media.filename())
            legenda = text or None
            if media.media_type == MediaType.PHOTO:
                await bot.send_photo(chat_id=telegram_id, photo=arquivo, caption=legenda)
            elif media.media_type == MediaType.VIDEO:
                await bot.send_video(chat_id=telegram_id, video=arquivo, caption=legenda)
            elif media.media_type == MediaType.VOICE:
                await bot.send_voice(chat_id=telegram_id, voice=arquivo, caption=legenda)
            elif media.media_type == MediaType.AUDIO:
                await bot.send_audio(chat_id=telegram_id, audio=arquivo, caption=legenda)
            else:
                logger.warning(
                    "tipo de midia desconhecido; enviando so o texto",
                    extra={"event": "MEDIA_TYPE_UNKNOWN", "type": media.media_type},
                )
                await _fallback_texto(bot, telegram_id, text, True)
        else:
            await _fallback_texto(bot, telegram_id, text, media_id is not None)
        return {"sent": True, "message_id": message_id}
    except Exception as exc:
        tries = ctx.get("job_try", 1)
        logger.warning(
            "falha ao enviar mensagem no telegram",
            extra={"event": "TELEGRAM_SEND_FAILED", "try": tries, "error": type(exc).__name__},
        )
        if tries >= MAX_TRIES:
            await _to_dead_letter(
                ctx,
                "send_telegram_message",
                type(exc).__name__,
                {"telegram_id": telegram_id, "message_id": message_id},
            )
            return {"sent": False, "dead_letter": True}
        raise Retry(defer=tries * 10) from exc
    finally:
        await bot.session.close()


async def send_followup(ctx: dict[str, Any], lead_id: int) -> dict[str, Any]:
    """Follow-up de lead parado no funil (CU4).

    Nao envia sem consentimento vigente — a checagem acontece aqui, no
    momento do envio, e nao no agendamento: o usuario pode ter revogado
    entre uma coisa e outra.
    """
    from app.bot.texts import FOLLOWUP

    async with SessionLocal() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None or lead.tenant_id != settings.tenant_id:
            return {"skipped": "lead inexistente"}

        user = await session.get(TelegramUser, lead.telegram_user_id)
        if user is None or user.is_blocked:
            return {"skipped": "usuario indisponivel"}

        if not await funnel_service.has_active_consent(session, user.id):
            logger.info(
                "follow-up abortado por falta de consentimento vigente",
                extra={"event": "FOLLOWUP_BLOCKED", "lead_id": lead_id},
            )
            return {"skipped": "sem consentimento vigente"}

        if FunnelState(user.current_state) in (FunnelState.CONVERTED, FunnelState.EXIT):
            return {"skipped": "funil encerrado"}

        # Idempotencia deterministica: um follow-up por lead por dia.
        day = datetime.now(UTC).date().isoformat()
        if not await claim(session, "followup", f"{lead_id}:{day}"):
            await session.commit()
            return {"skipped": "ja enviado hoje"}

        await record_event(
            session, EventType.FOLLOWUP_SENT, telegram_user_id=user.id, lead_id=lead.id
        )
        conversation = await conversation_service.get_or_create_conversation(session, user.id)
        await conversation_service.record_message(
            session,
            conversation,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.BOT,
            content=FOLLOWUP,
        )
        await session.commit()
        telegram_id = user.telegram_id

    await send_telegram_message(ctx, telegram_id, FOLLOWUP)
    return {"sent": True, "lead_id": lead_id}


async def schedule_followups(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: agenda follow-up para leads parados.

    Roda a cada 15 minutos e so considera lead com consentimento aceito e
    interacao antiga o suficiente.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.followup_delay_minutes)
    scheduled = 0

    async with SessionLocal() as session:
        stmt = (
            select(Lead)
            .join(TelegramUser, TelegramUser.id == Lead.telegram_user_id)
            .where(
                Lead.tenant_id == settings.tenant_id,
                Lead.converted_at.is_(None),
                Lead.last_interaction_at.is_not(None),
                Lead.last_interaction_at < cutoff,
                TelegramUser.is_blocked.is_(False),
                TelegramUser.current_state.in_(
                    [FunnelState.QUALIFICATION, FunnelState.INFORMATION]
                ),
            )
            .limit(200)
        )
        leads = list((await session.execute(stmt)).scalars())

        for lead in leads:
            if not await funnel_service.has_active_consent(session, lead.telegram_user_id):
                continue
            await record_event(
                session,
                EventType.FOLLOWUP_SCHEDULED,
                telegram_user_id=lead.telegram_user_id,
                lead_id=lead.id,
            )
            await ctx["redis"].enqueue_job("send_followup", lead.id)
            scheduled += 1
        await session.commit()

    logger.info("follow-ups agendados", extra={"event": "FOLLOWUP_BATCH", "count": scheduled})
    return {"scheduled": scheduled}


async def notify_external(ctx: dict[str, Any], event: str, payload: dict[str, Any]) -> dict:
    """Notifica integracao externa (n8n).

    Camada opcional: sem URL configurada o job simplesmente nao faz nada, e
    uma falha aqui nunca afeta bot, API ou dashboard (M20).
    """
    if not settings.n8n_webhook_url:
        return {"skipped": "integracao nao configurada"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                settings.n8n_webhook_url,
                json={"tenant_id": settings.tenant_id, "event": event, "payload": payload},
            )
            response.raise_for_status()
        return {"sent": True}
    except Exception as exc:
        tries = ctx.get("job_try", 1)
        if tries >= MAX_TRIES:
            await _to_dead_letter(ctx, "notify_external", type(exc).__name__, {"event": event})
            return {"sent": False, "dead_letter": True}
        raise Retry(defer=tries * 30) from exc


async def aggregate_metrics(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron horario: consolida indicadores no Redis para leitura rapida."""
    import json

    from app.services import analytics_service

    async with SessionLocal() as session:
        snapshot = await analytics_service.overview(session, days=30)

    await ctx["redis"].set(
        f"metrics:{settings.tenant_id}:overview", json.dumps(snapshot), ex=3600
    )
    return snapshot


async def startup(ctx: dict[str, Any]) -> None:
    setup_logging("worker")
    settings.validate_runtime("worker")
    logger.info("worker iniciado", extra={"event": "WORKER_STARTED"})


async def shutdown(ctx: dict[str, Any]) -> None:
    from app.core.database import engine

    await engine.dispose()


class WorkerSettings:
    """Configuracao consumida por `arq app.workers.tasks.WorkerSettings`."""

    functions = [send_telegram_message, send_followup, notify_external]
    cron_jobs: list = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_tries = MAX_TRIES
    health_check_interval = 30
    job_timeout = 120


def _build_cron() -> list:
    from arq import cron

    return [
        cron(schedule_followups, minute={0, 15, 30, 45}, run_at_startup=False),
        cron(aggregate_metrics, minute=5, run_at_startup=True),
    ]


WorkerSettings.cron_jobs = _build_cron()
WorkerSettings.functions.extend([schedule_followups, aggregate_metrics])
