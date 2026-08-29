"""Logging estruturado em JSON com contexto de empresa/tenant.

Todo log carrega company, tenant_id e service (planejamento/ordens.md, M4).
Segredos nunca entram no log: o filtro abaixo remove chaves sensiveis dos
campos extras antes da serializacao.
"""

import logging
import sys
from typing import Any

try:
    from pythonjsonlogger import json as jsonlogger
except ImportError:  # python-json-logger < 3
    from pythonjsonlogger import jsonlogger

from app.core.config import settings

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "telegram_bot_token",
    "jwt_secret",
    "encryption_key",
    "secret",
    "authorization",
    "totp_secret",
    "x-signature",
    "x-telegram-bot-api-secret-token",
}


class ContextFormatter(jsonlogger.JsonFormatter):
    def __init__(self, *args: Any, service: str = "api", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.service = service

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["company"] = settings.company_slug
        log_record["tenant_id"] = settings.tenant_id
        log_record["service"] = self.service
        log_record["level"] = record.levelname
        log_record.setdefault("event", record.name)
        for key in list(log_record):
            if key.lower() in SENSITIVE_KEYS:
                log_record[key] = "[REDACTED]"


def setup_logging(service: str = "api") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", service=service)
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)
    # Uvicorn duplica logs se mantiver os proprios handlers.
    for noisy in ("uvicorn.access", "uvicorn.error", "aiogram.event"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
