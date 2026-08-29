"""Primitivas de seguranca: hash de senha, JWT, assinatura de webhook, hash de IP.

Regras aplicadas aqui (planejamento/regras.md):
- senha com Argon2, nunca SHA puro;
- access token curto + refresh com rotacao;
- validacao de assinatura HMAC e janela de timestamp (anti-replay);
- IP sempre armazenado como hash, nunca em texto plano.
"""

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_password_hash = PasswordHash.recommended()

ALGORITHM = "HS256"


# --------------------------------------------------------------------------- senha
def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------- JWT
def _encode(payload: dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    body = {
        **payload,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
        "type": token_type,
        "tenant_id": settings.tenant_id,
    }
    return jwt.encode(body, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(operator_id: int, role: str) -> str:
    """Access token curto.

    O papel vai no claim apenas como atalho de UI. Toda acao privilegiada
    reconsulta a linha do operador no banco antes de autorizar.
    """
    return _encode(
        {"sub": str(operator_id), "role": role},
        timedelta(minutes=settings.access_token_ttl_minutes),
        "access",
    )


def create_refresh_token(operator_id: int) -> str:
    return _encode(
        {"sub": str(operator_id)},
        timedelta(days=settings.refresh_token_ttl_days),
        "refresh",
    )


#: Janela para concluir o cadastro do 2FA. Curta de proposito: e o intervalo
#: em que a senha sozinha permite escanear o QR.
ENROLLMENT_TTL_MINUTES = 5


def create_enrollment_token(operator_id: int) -> str:
    """Token de uso unico para concluir o cadastro do 2FA.

    Nao carrega o segredo — so identifica o operador. O segredo provisorio
    fica no banco e e lido na confirmacao. O claim `type` impede que este
    token sirva de access token em qualquer outra rota.
    """
    return _encode(
        {"sub": str(operator_id)},
        timedelta(minutes=ENROLLMENT_TTL_MINUTES),
        "enroll",
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decodifica e valida o token. Lanca jwt.PyJWTError se invalido."""
    payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("tipo de token inesperado")
    if payload.get("tenant_id") != settings.tenant_id:
        raise jwt.InvalidTokenError("tenant do token nao confere com o deployment")
    return payload


# ------------------------------------------------------------------------ webhooks
def sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 sobre "<timestamp>." + corpo bruto."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return mac.hexdigest()


def verify_webhook_signature(
    secret: str, timestamp: str, body: bytes, signature: str
) -> tuple[bool, str]:
    """Valida assinatura e janela de tempo. Retorna (ok, motivo_da_falha)."""
    if not secret:
        return False, "webhook secret nao configurado"
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False, "timestamp invalido"
    drift = abs(int(time.time()) - ts)
    if drift > settings.webhook_timestamp_tolerance_seconds:
        return False, "timestamp fora da janela de tolerancia (replay)"
    expected = sign_payload(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature or ""):
        return False, "assinatura invalida"
    return True, ""


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")


# --------------------------------------------------------------------------- misc
def hash_ip(ip: str | None) -> str | None:
    """Hash do IP com sal derivado do encryption_key. Nunca guardamos IP cru."""
    if not ip:
        return None
    salt = settings.encryption_key or settings.company_slug
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def generate_tracking_token() -> str:
    """Token opaco de rastreamento. Nao carrega nenhum dado interno."""
    return "t_" + secrets.token_urlsafe(12)
