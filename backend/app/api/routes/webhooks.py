"""Webhooks de entrada.

Toda rota daqui e publica na internet. Ordem obrigatoria de verificacao,
antes de qualquer efeito colateral (planejamento/regras.md):

  rate limit -> assinatura/segredo -> janela de timestamp (anti-replay)
  -> idempotencia -> efeito

Erro de validacao nunca detalha o motivo para o cliente; o motivo vai para o
log interno.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import SessionDep, client_ip, rate_limit
from app.core.config import settings
from app.core.enums import LeadStatus
from app.core.logging import get_logger
from app.core.security import constant_time_equals, verify_webhook_signature
from app.models import Lead, TelegramUser
from app.schemas import ConversionWebhook
from app.services.conversion_service import ConversionError, register_conversion
from app.services.idempotency_service import claim

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


@router.post("/telegram", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    """Recebe updates do Telegram em producao.

    Autenticacao pelo secret_token configurado no setWebhook — a URL sozinha
    nao e segredo. Em desenvolvimento o bot roda em polling e esta rota fica
    desabilitada.
    """
    await rate_limit(request, "webhook", settings.rate_limit_webhook_per_minute)

    if not settings.telegram_use_webhook:
        raise HTTPException(status_code=404, detail="nao encontrado")

    if not constant_time_equals(
        x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret
    ):
        logger.warning("update do telegram com secret token invalido descartado")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nao autorizado")

    dispatcher = getattr(request.app.state, "dispatcher", None)
    bot = getattr(request.app.state, "bot", None)
    if dispatcher is None or bot is None:
        raise HTTPException(status_code=503, detail="bot indisponivel")

    from aiogram.types import Update

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return Response(status_code=status.HTTP_200_OK)


@router.post("/conversion")
async def conversion_webhook(
    request: Request,
    session: SessionDep,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Conversao vinda de provedor externo (CU3)."""
    await rate_limit(request, "webhook", settings.rate_limit_webhook_per_minute)

    raw_body = await request.body()
    ok, reason = verify_webhook_signature(
        settings.conversion_webhook_secret, x_timestamp or "", raw_body, x_signature or ""
    )
    if not ok:
        logger.warning(
            "webhook de conversao rejeitado",
            extra={"event": "WEBHOOK_REJECTED", "reason": reason, "ip": client_ip(request)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nao autorizado")

    if not x_idempotency_key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key obrigatorio")

    try:
        payload = ConversionWebhook.model_validate_json(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="payload invalido") from exc

    # Idempotencia antes do efeito. Reentrega devolve 200 sem reprocessar.
    if not await claim(session, "conversion", x_idempotency_key):
        await session.commit()
        logger.info("webhook de conversao reentregue; ignorado", extra={"event": "WEBHOOK_DUP"})
        return {"status": "duplicate", "processed": False}

    lead = await _resolve_lead(session, payload)
    if lead is None:
        await session.commit()
        raise HTTPException(status_code=404, detail="lead nao encontrado")

    try:
        _, created = await register_conversion(
            session,
            lead_id=lead.id,
            external_id=payload.external_id,
            conversion_type=payload.conversion_type,
            value=payload.value,
            currency=payload.currency,
            metadata=payload.metadata,
        )
    except ConversionError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await session.commit()
    return {"status": "ok", "processed": created, "lead_id": lead.id}


async def _resolve_lead(session: SessionDep, payload: ConversionWebhook) -> Lead | None:
    if payload.lead_id is not None:
        lead = await session.get(Lead, payload.lead_id)
        return lead if lead and lead.tenant_id == settings.tenant_id else None

    if payload.telegram_id is not None:
        user = (
            await session.execute(
                select(TelegramUser).where(
                    TelegramUser.telegram_id == payload.telegram_id,
                    TelegramUser.tenant_id == settings.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if user is None:
            return None
        return (
            await session.execute(
                select(Lead).where(
                    Lead.telegram_user_id == user.id,
                    Lead.tenant_id == settings.tenant_id,
                )
            )
        ).scalar_one_or_none()
    return None


@router.post("/external/{provider}")
async def external_webhook(
    provider: str,
    request: Request,
    session: SessionDep,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Entrada generica para provedores externos.

    Mesma disciplina de seguranca do webhook de conversao. O corpo e apenas
    registrado como evento — o processamento especifico por provedor entra
    quando houver integracao real, sem afrouxar a validacao.
    """
    await rate_limit(request, "webhook", settings.rate_limit_webhook_per_minute)

    if provider not in {"n8n", "meta", "google"}:
        raise HTTPException(status_code=404, detail="provedor nao suportado")

    raw_body = await request.body()
    ok, reason = verify_webhook_signature(
        settings.conversion_webhook_secret, x_timestamp or "", raw_body, x_signature or ""
    )
    if not ok:
        logger.warning(
            "webhook externo rejeitado",
            extra={"event": "WEBHOOK_REJECTED", "provider": provider, "reason": reason},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nao autorizado")

    if not x_idempotency_key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key obrigatorio")

    if not await claim(session, f"external:{provider}", x_idempotency_key):
        await session.commit()
        return {"status": "duplicate", "processed": False}

    await session.commit()
    logger.info("webhook externo aceito", extra={"event": "WEBHOOK_RECEIVED", "provider": provider})
    return {"status": "ok", "processed": True}


__all__ = ["router", "LeadStatus"]
