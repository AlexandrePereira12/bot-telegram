"""Cadastro de 2FA no primeiro acesso.

Caminho de autenticacao: cada garantia aqui tem teste proprio.
"""

import jwt
import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OperatorRole
from app.core.security import create_access_token, create_enrollment_token, decode_token
from app.services.auth_service import (
    AuthError,
    confirm_enrollment,
    create_operator,
    requires_2fa,
    start_enrollment,
    verify_credentials,
    verify_totp,
)

SENHA = "senha-de-teste-1234"


async def _admin(session: AsyncSession, email: str = "admin@teste.com"):
    operator = await create_operator(
        session, email=email, password=SENHA, role=OperatorRole.ADMIN
    )
    await session.flush()
    return operator


async def _enrolled_admin(session: AsyncSession, email: str = "admin@teste.com"):
    operator = await _admin(session, email)
    start_enrollment(operator)
    confirm_enrollment(operator, pyotp.TOTP(operator.totp_secret).now())
    await session.flush()
    return operator


# -------------------------------------------------------------- estado inicial
async def test_admin_nasce_sem_segredo_e_com_cadastro_pendente(session: AsyncSession):
    """O segredo nao existe antes do primeiro acesso."""
    operator = await _admin(session)
    assert operator.totp_secret is None
    assert operator.totp_confirmed_at is None
    assert operator.totp_pending is True
    assert requires_2fa(operator) is True


async def test_perfil_sem_2fa_nao_entra_no_fluxo(session: AsyncSession):
    operator = await create_operator(
        session, email="manager@teste.com", password=SENHA, role=OperatorRole.MANAGER
    )
    assert requires_2fa(operator) is False


# ------------------------------------------------------------------- cadastro
async def test_senha_correta_libera_o_cadastro(session: AsyncSession):
    await _admin(session)
    operator = await verify_credentials(session, "admin@teste.com", SENHA)

    uri = start_enrollment(operator)
    assert operator.totp_secret is not None
    assert uri.startswith("otpauth://totp/")
    assert operator.totp_secret in uri
    assert operator.totp_pending is True, "so confirma depois do primeiro codigo"


async def test_senha_errada_nao_chega_ao_cadastro(session: AsyncSession):
    await _admin(session)
    with pytest.raises(AuthError):
        await verify_credentials(session, "admin@teste.com", "senha-errada-123")


async def test_confirmacao_com_codigo_valido_conclui(session: AsyncSession):
    operator = await _admin(session)
    start_enrollment(operator)

    confirm_enrollment(operator, pyotp.TOTP(operator.totp_secret).now())

    assert operator.totp_confirmed_at is not None
    assert operator.totp_pending is False


async def test_confirmacao_com_codigo_errado_mantem_pendente(session: AsyncSession):
    operator = await _admin(session)
    start_enrollment(operator)

    with pytest.raises(AuthError, match="codigo invalido"):
        confirm_enrollment(operator, "000000")

    assert operator.totp_confirmed_at is None, "cadastro segue pendente"


async def test_confirmar_sem_iniciar_falha(session: AsyncSession):
    operator = await _admin(session)
    with pytest.raises(AuthError, match="nao iniciado"):
        confirm_enrollment(operator, "123456")


# ------------------------------------------------------ protecao pos-cadastro
async def test_segredo_nao_pode_ser_trocado_depois_de_confirmado(session: AsyncSession):
    """Quem tem so a senha nao substitui o autenticador de um admin ativo."""
    operator = await _enrolled_admin(session)
    original = operator.totp_secret

    with pytest.raises(AuthError, match="ja cadastrado"):
        start_enrollment(operator)
    assert operator.totp_secret == original


async def test_confirmar_duas_vezes_e_recusado(session: AsyncSession):
    operator = await _enrolled_admin(session)
    with pytest.raises(AuthError, match="ja cadastrado"):
        confirm_enrollment(operator, pyotp.TOTP(operator.totp_secret).now())


# ----------------------------------------------------------- login depois
async def test_login_confirmado_exige_codigo(session: AsyncSession):
    operator = await _enrolled_admin(session)
    with pytest.raises(AuthError, match="obrigatorio"):
        verify_totp(operator, None)


async def test_login_confirmado_recusa_codigo_errado(session: AsyncSession):
    operator = await _enrolled_admin(session)
    with pytest.raises(AuthError):
        verify_totp(operator, "000000")


async def test_login_confirmado_aceita_codigo_do_app(session: AsyncSession):
    operator = await _enrolled_admin(session)
    verify_totp(operator, pyotp.TOTP(operator.totp_secret).now())


async def test_verify_totp_recusa_quem_ainda_nao_cadastrou(session: AsyncSession):
    operator = await _admin(session)
    start_enrollment(operator)
    # Codigo correto, mas cadastro nao confirmado: nao serve para logar.
    with pytest.raises(AuthError, match="nao cadastrado"):
        verify_totp(operator, pyotp.TOTP(operator.totp_secret).now())


# ------------------------------------------------------- token de enrollment
def test_token_de_enrollment_nao_serve_como_access_token():
    token = create_enrollment_token(42)
    assert decode_token(token, "enroll")["sub"] == "42"
    with pytest.raises(jwt.InvalidTokenError, match="tipo de token"):
        decode_token(token, "access")


def test_access_token_nao_serve_para_confirmar_2fa():
    token = create_access_token(42, "ADMIN")
    with pytest.raises(jwt.InvalidTokenError, match="tipo de token"):
        decode_token(token, "enroll")


def test_token_de_enrollment_nao_carrega_o_segredo():
    """O segredo fica no banco; o token so identifica o operador."""
    secret = pyotp.random_base32()
    token = create_enrollment_token(42)
    assert secret not in token
    claims = decode_token(token, "enroll")
    assert set(claims) == {"sub", "iat", "exp", "jti", "type", "tenant_id"}
