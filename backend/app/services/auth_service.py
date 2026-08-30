"""Autenticacao de operador e RBAC (M16)."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pyotp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import OperatorRole
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import Operator

logger = get_logger(__name__)

#: Perfis que podem escrever em cada dominio. Consultado a cada requisicao
#: contra a linha do operador no banco — nunca so pelo claim do JWT.
PERMISSIONS: dict[str, set[OperatorRole]] = {
    "campaigns:read": {
        OperatorRole.ADMIN,
        OperatorRole.MANAGER,
        OperatorRole.ANALYST,
    },
    "campaigns:write": {OperatorRole.ADMIN, OperatorRole.MANAGER},
    "leads:read": {
        OperatorRole.ADMIN,
        OperatorRole.MANAGER,
        OperatorRole.ANALYST,
        OperatorRole.OPERATOR,
        OperatorRole.SUPPORT,
    },
    "conversations:read": {
        OperatorRole.ADMIN,
        OperatorRole.MANAGER,
        OperatorRole.OPERATOR,
        OperatorRole.SUPPORT,
    },
    "conversations:write": {
        OperatorRole.ADMIN,
        OperatorRole.OPERATOR,
        OperatorRole.SUPPORT,
    },
    "analytics:read": {
        OperatorRole.ADMIN,
        OperatorRole.MANAGER,
        OperatorRole.ANALYST,
    },
    "events:write": {OperatorRole.ADMIN, OperatorRole.MANAGER},
    "admin:write": {OperatorRole.ADMIN},
}


class AuthError(Exception):
    """Falha de autenticacao. Mensagem sempre generica para o cliente."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def has_permission(role: OperatorRole, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


async def get_operator_by_email(session: AsyncSession, email: str) -> Operator | None:
    stmt = select(Operator).where(
        func.lower(Operator.email) == email.strip().lower(),
        Operator.tenant_id == settings.tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


#: Perfis que exigem 2FA. Hoje so ADMIN (planejamento/regras.md).
ROLES_REQUIRING_2FA = {OperatorRole.ADMIN}


def requires_2fa(operator: Operator) -> bool:
    return operator.role in ROLES_REQUIRING_2FA


async def verify_credentials(session: AsyncSession, email: str, password: str) -> Operator:
    """Valida apenas e-mail e senha.

    O 2FA e decidido pela rota, porque o desfecho depende do estado do
    cadastro: pendente leva ao QR, confirmado exige o codigo. Erro nunca
    revela se o e-mail existe.
    """
    operator = await get_operator_by_email(session, email)

    if operator is None:
        # Gasta o mesmo tempo de um hash real para nao expor a existencia da
        # conta por diferenca de latencia.
        verify_password(password, hash_password("dummy"))
        raise AuthError("credenciais invalidas")

    if not operator.is_active:
        raise AuthError("credenciais invalidas")

    if not verify_password(password, operator.password_hash):
        raise AuthError("credenciais invalidas")

    return operator


def verify_totp(operator: Operator, totp_code: str | None) -> None:
    """Exige o codigo de 6 digitos de quem ja concluiu o cadastro do 2FA."""
    if not operator.totp_secret or operator.totp_pending:
        raise AuthError("2FA nao cadastrado")
    if not totp_code:
        raise AuthError("codigo 2FA obrigatorio")
    if not pyotp.TOTP(operator.totp_secret).verify(totp_code, valid_window=1):
        raise AuthError("credenciais invalidas")


def start_enrollment(operator: Operator) -> str:
    """Gera (ou regera) o segredo provisorio e devolve a URI otpauth.

    So vale enquanto o cadastro esta pendente: depois de confirmado, quem
    tiver apenas a senha nao consegue trocar o segredo por um proprio.
    """
    if not operator.totp_pending:
        raise AuthError("2FA ja cadastrado")
    operator.totp_secret = pyotp.random_base32()
    return pyotp.TOTP(operator.totp_secret).provisioning_uri(
        name=operator.email, issuer_name=f"TrafficBot ({settings.company_name})"
    )


def confirm_enrollment(operator: Operator, totp_code: str) -> None:
    """Conclui o cadastro validando o primeiro codigo gerado pelo app."""
    if not operator.totp_pending:
        raise AuthError("2FA ja cadastrado")
    if not operator.totp_secret:
        raise AuthError("cadastro de 2FA nao iniciado")
    if not pyotp.TOTP(operator.totp_secret).verify(totp_code, valid_window=1):
        raise AuthError("codigo invalido")
    operator.totp_confirmed_at = datetime.now(UTC)


def issue_tokens(operator: Operator) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(operator.id, operator.role.value),
        refresh_token=create_refresh_token(operator.id),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def count_active_admins(session: AsyncSession, *, excluding: int | None = None) -> int:
    """Quantos ADMIN ativos restam no tenant.

    Base do guarda de ultimo administrador: rebaixar, desativar ou excluir o
    unico ADMIN ativo tranca a instalacao — depois disso so a CLI, com acesso
    ao servidor, consegue criar outro.
    """
    stmt = select(func.count(Operator.id)).where(
        Operator.tenant_id == settings.tenant_id,
        Operator.role == OperatorRole.ADMIN,
        Operator.is_active.is_(True),
    )
    if excluding is not None:
        stmt = stmt.where(Operator.id != excluding)
    return (await session.execute(stmt)).scalar_one()


async def ensure_admin_remains(session: AsyncSession, *, excluding: int) -> None:
    """Recusa a operacao que deixaria o tenant sem nenhum ADMIN ativo."""
    if await count_active_admins(session, excluding=excluding) == 0:
        raise AuthError("esta e a unica conta de administrador ativa")


def reset_totp(operator: Operator) -> None:
    """Descarta o cadastro do 2FA (celular perdido ou trocado).

    O segredo antigo nao e reexibido: e simplesmente descartado, e o operador
    cadastra outro no proximo login pelo mesmo fluxo de QR do primeiro acesso.
    """
    operator.totp_secret = None
    operator.totp_confirmed_at = None


async def create_operator(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: OperatorRole,
    full_name: str | None = None,
) -> Operator:
    if await get_operator_by_email(session, email):
        raise AuthError("operador ja existe")
    operator = Operator(
        tenant_id=settings.tenant_id,
        email=email.strip().lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    session.add(operator)
    await session.flush()
    return operator
