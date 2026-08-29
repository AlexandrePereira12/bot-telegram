"""Idempotencia, RBAC, assinatura de webhook e templates de mensagem."""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OperatorRole
from app.core.security import (
    hash_ip,
    hash_password,
    sign_payload,
    verify_password,
    verify_webhook_signature,
)
from app.services import lead_service
from app.services.auth_service import has_permission
from app.services.conversion_service import register_conversion
from app.services.idempotency_service import claim
from app.services.tracking_service import ORGANIC


# ---------------------------------------------------------------- idempotencia
async def test_chave_de_idempotencia_so_e_aceita_uma_vez(session: AsyncSession):
    assert await claim(session, "conversion", "abc123") is True
    assert await claim(session, "conversion", "abc123") is False
    # Escopos diferentes nao colidem.
    assert await claim(session, "events", "abc123") is True


async def test_conversao_duplicada_nao_cria_segunda_linha(
    session: AsyncSession, campaign
):
    user, _ = await lead_service.get_or_create_user(session, telegram_id=3001)
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    await session.flush()

    _, created_first = await register_conversion(
        session, lead_id=lead.id, external_id="ext-1", value=100.0, currency="BRL"
    )
    _, created_again = await register_conversion(
        session, lead_id=lead.id, external_id="ext-1", value=100.0, currency="BRL"
    )
    assert created_first is True
    assert created_again is False, "reentrega do mesmo external_id nao duplica conversao"


# ------------------------------------------------------------------------ RBAC
def test_analyst_nao_escreve_em_campanha():
    assert has_permission(OperatorRole.ANALYST, "campaigns:read") is True
    assert has_permission(OperatorRole.ANALYST, "campaigns:write") is False


def test_support_nao_acessa_analytics_nem_admin():
    assert has_permission(OperatorRole.SUPPORT, "conversations:write") is True
    assert has_permission(OperatorRole.SUPPORT, "analytics:read") is False
    assert has_permission(OperatorRole.SUPPORT, "admin:write") is False


def test_admin_tem_todas_as_permissoes():
    from app.services.auth_service import PERMISSIONS

    for permission in PERMISSIONS:
        assert has_permission(OperatorRole.ADMIN, permission), permission


# -------------------------------------------------------------------- webhooks
def test_assinatura_valida_e_aceita():
    body = b'{"external_id":"x"}'
    ts = str(int(time.time()))
    signature = sign_payload("segredo", ts, body)
    ok, _ = verify_webhook_signature("segredo", ts, body, signature)
    assert ok is True


def test_assinatura_invalida_e_rejeitada():
    body = b'{"external_id":"x"}'
    ts = str(int(time.time()))
    ok, reason = verify_webhook_signature("segredo", ts, body, "deadbeef")
    assert ok is False
    assert "assinatura" in reason


def test_timestamp_antigo_e_rejeitado_como_replay():
    body = b'{"external_id":"x"}'
    old = str(int(time.time()) - 4000)
    signature = sign_payload("segredo", old, body)
    ok, reason = verify_webhook_signature("segredo", old, body, signature)
    assert ok is False
    assert "replay" in reason


def test_corpo_adulterado_invalida_assinatura():
    ts = str(int(time.time()))
    signature = sign_payload("segredo", ts, b'{"value":10}')
    ok, _ = verify_webhook_signature("segredo", ts, b'{"value":9999}', signature)
    assert ok is False


# --------------------------------------------------------------------- senhas
def test_hash_de_senha_nao_e_reversivel_e_verifica():
    hashed = hash_password("senha-de-teste-123")
    assert hashed != "senha-de-teste-123"
    assert hashed.startswith("$argon2")
    assert verify_password("senha-de-teste-123", hashed) is True
    assert verify_password("senha-errada", hashed) is False


def test_ip_e_armazenado_como_hash():
    hashed = hash_ip("203.0.113.10")
    assert hashed is not None
    assert "203.0.113.10" not in hashed
    assert len(hashed) == 64
    assert hash_ip(None) is None


# ------------------------------------------------------------------ compliance
TERMOS_PROIBIDOS = [
    "ganho garantido",
    "lucro certo",
    "dinheiro facil",
    "sem risco",
    "aposte agora",
    "renda garantida",
    "voce vai ganhar",
]


def test_templates_do_bot_nao_prometem_ganho():
    """Compliance jogos/apostas: nenhum template promete resultado."""
    from app.bot import texts

    conteudo = " ".join(
        value.lower()
        for name, value in vars(texts).items()
        if isinstance(value, str) and not name.startswith("_")
    )
    for termo in TERMOS_PROIBIDOS:
        assert termo not in conteudo, f"template promete resultado: {termo}"


def test_age_gate_menciona_idade_minima():
    from app.bot import texts
    from app.core.config import settings

    assert str(settings.min_age) in texts.age_gate()
    assert str(settings.min_age) in texts.age_rejected()


def test_logging_redige_campos_sensiveis():
    from app.core.logging import SENSITIVE_KEYS

    for chave in ("password", "token", "jwt_secret", "telegram_bot_token", "authorization"):
        assert chave in SENSITIVE_KEYS
