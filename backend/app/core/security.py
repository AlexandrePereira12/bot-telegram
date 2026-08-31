"""Primitivas de seguranca: hash de senha, JWT, assinatura de webhook, hash de IP.

Regras aplicadas aqui (planejamento/regras.md):
- senha com Argon2, nunca SHA puro;
- access token curto + refresh com rotacao;
- validacao de assinatura HMAC e janela de timestamp (anti-replay);
- IP sempre armazenado como hash, nunca em texto plano.
"""

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
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


# ------------------------------------------------------------------- segredos
#
# Segredo de integracao (chave de API de provedor de IA) precisa VOLTAR ao
# claro: o bot usa a chave para chamar o servico. Por isso e cifrado, e nao
# hasheado — hash resolveria "ninguem le", mas tambem impediria a aplicacao de
# usar a chave. O que o painel mostra e uma mascara, nunca o valor.


def _fernet() -> Any:
    """Cifrador derivado do ENCRYPTION_KEY.

    A chave do Fernet precisa ter 32 bytes em base64 urlsafe; o valor do .env e
    texto livre, entao passa por SHA-256 antes. Derivar em vez de exigir
    formato especifico evita que uma instalacao existente precise trocar o
    segredo para ganhar a funcionalidade.
    """
    from cryptography.fernet import Fernet

    material = settings.encryption_key
    if not material:
        # Fallback para nao quebrar instalacao que subiu sem ENCRYPTION_KEY.
        # Registrado porque a falha seguinte seria pessima de diagnosticar:
        # trocar o JWT_SECRET (rotina de rotacao) tornaria ilegivel toda chave
        # ja cifrada, e o sintoma apareceria como "a IA parou de responder".
        material = settings.jwt_secret
        if material:
            _avisar_fallback()
    if not material:
        raise RuntimeError(
            "ENCRYPTION_KEY ausente: sem ela nao ha como guardar segredo de "
            "integracao com seguranca"
        )
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


@lru_cache(maxsize=1)
def _avisar_fallback() -> None:
    """Aviso emitido uma vez por processo, nao a cada segredo cifrado."""
    from app.core.logging import get_logger

    get_logger(__name__).warning(
        "ENCRYPTION_KEY ausente: segredos de integracao estao cifrados com o "
        "JWT_SECRET. Trocar o JWT_SECRET tornara as chaves ja guardadas "
        "ilegiveis — defina ENCRYPTION_KEY.",
        extra={"event": "ENCRYPTION_KEY_MISSING"},
    )


def encrypt_secret(value: str) -> str:
    """Cifra um segredo para guardar no banco."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Recupera o segredo. Lanca se o ENCRYPTION_KEY nao for o mesmo da escrita."""
    return _fernet().decrypt(value.encode()).decode()


def mask_secret(value: str, visible: int = 4) -> str:
    """Mascara para exibicao: prefixo curto, fim visivel, meio escondido.

    Mostrar o comeco e o fim e o que permite a pessoa reconhecer *qual* chave
    esta ali sem que a tela exponha o segredo — e o suficiente para conferir se
    trocaram a chave por outra.
    """
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "•" * len(value)
    return f"{value[:visible]}{'•' * 8}{value[-visible:]}"


def generate_tracking_token() -> str:
    """Token opaco de rastreamento. Nao carrega nenhum dado interno."""
    return "t_" + secrets.token_urlsafe(12)
