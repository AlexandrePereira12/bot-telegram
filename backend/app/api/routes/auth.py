"""Rotas de autenticacao."""

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import OperatorDep, SessionDep, client_ip, rate_limit
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    ENROLLMENT_TTL_MINUTES,
    create_enrollment_token,
    decode_token,
    hash_ip,
)
from app.models import Operator
from app.schemas import (
    Enroll2FARequest,
    EnrollmentResponse,
    LoginRequest,
    OperatorOut,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth_service import (
    AuthError,
    confirm_enrollment,
    issue_tokens,
    requires_2fa,
    start_enrollment,
    verify_credentials,
    verify_totp,
)
from app.services.event_service import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


async def _login_rate_limit(request: Request) -> None:
    await rate_limit(request, "login", settings.rate_limit_login_per_minute)


@router.post("/login", dependencies=[Depends(_login_rate_limit)])
async def login(
    payload: LoginRequest, request: Request, session: SessionDep
) -> TokenResponse | EnrollmentResponse:
    """Login.

    Devolve os tokens normalmente, ou — no primeiro acesso de um perfil que
    exige 2FA — o material para o cadastro do autenticador, sem emitir
    nenhum token de sessao.
    """
    ip_hash = hash_ip(client_ip(request))
    try:
        operator = await verify_credentials(session, payload.email, payload.password)
    except AuthError as exc:
        await record_audit(
            session,
            actor_id=None,
            action="login",
            resource_type="operator",
            result="failure",
            # Nunca registramos senha nem o codigo 2FA.
            metadata={"reason": str(exc)},
            ip_hash=ip_hash,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="credenciais invalidas"
        ) from exc

    if requires_2fa(operator):
        if operator.totp_pending:
            # Senha correta e 2FA ainda nao cadastrado: entrega o QR. E o
            # unico momento em que o segredo sai do servidor.
            otpauth_uri = start_enrollment(operator)
            await record_audit(
                session,
                actor_id=operator.id,
                action="2fa_enrollment_started",
                resource_type="operator",
                resource_id=operator.id,
                ip_hash=ip_hash,
            )
            await session.commit()
            return EnrollmentResponse(
                enrollment_token=create_enrollment_token(operator.id),
                otpauth_uri=otpauth_uri,
                secret=operator.totp_secret or "",
                expires_in=ENROLLMENT_TTL_MINUTES * 60,
            )
        try:
            verify_totp(operator, payload.totp_code)
        except AuthError as exc:
            await record_audit(
                session,
                actor_id=operator.id,
                action="login",
                resource_type="operator",
                resource_id=operator.id,
                result="failure",
                metadata={"reason": str(exc)},
                ip_hash=ip_hash,
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="credenciais invalidas"
            ) from exc

    tokens = issue_tokens(operator)
    await record_audit(
        session,
        actor_id=operator.id,
        action="login",
        resource_type="operator",
        resource_id=operator.id,
        ip_hash=ip_hash,
    )
    await session.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


async def _enroll_rate_limit(request: Request) -> None:
    # Confirmacao e um chute de 6 digitos: precisa de limite proprio, mais
    # apertado que o do login.
    await rate_limit(request, "enroll", settings.rate_limit_login_per_minute)


@router.post(
    "/2fa/confirm", response_model=TokenResponse, dependencies=[Depends(_enroll_rate_limit)]
)
async def confirm_2fa(
    payload: Enroll2FARequest, request: Request, session: SessionDep
) -> TokenResponse:
    """Conclui o cadastro do 2FA e ja autentica.

    Aceita apenas o token emitido pelo login (`type=enroll`, 5 min) e so
    enquanto o cadastro estiver pendente — depois de confirmado, ninguem
    troca o segredo tendo apenas a senha.
    """
    ip_hash = hash_ip(client_ip(request))
    try:
        claims = decode_token(payload.enrollment_token, "enroll")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="cadastro expirado; faca login novamente",
        ) from exc

    operator = await session.get(Operator, int(claims["sub"]))
    if operator is None or not operator.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nao autorizado")

    try:
        confirm_enrollment(operator, payload.totp_code)
    except AuthError as exc:
        await record_audit(
            session,
            actor_id=operator.id,
            action="2fa_confirm",
            resource_type="operator",
            resource_id=operator.id,
            result="failure",
            metadata={"reason": str(exc)},
            ip_hash=ip_hash,
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    tokens = issue_tokens(operator)
    await record_audit(
        session,
        actor_id=operator.id,
        action="2fa_confirmed",
        resource_type="operator",
        resource_id=operator.id,
        ip_hash=ip_hash,
    )
    await session.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenResponse:
    """Emite um par novo de tokens a partir de um refresh valido.

    Atencao: nao ha revogacao do refresh anterior — ele continua valido ate
    expirar (REFRESH_TOKEN_TTL_DAYS). Revogacao imediata exigiria uma lista
    de `jti` invalidados no Redis; enquanto isso nao existe, o corte de
    acesso efetivo e desativar o operador (`is_active=false`), o que bloqueia
    na hora porque toda requisicao reconsulta a linha no banco.
    """
    try:
        claims = decode_token(payload.refresh_token, "refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token invalido"
        ) from exc

    operator = await session.get(Operator, int(claims["sub"]))
    if operator is None or not operator.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token invalido"
        )

    tokens = issue_tokens(operator)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(operator: OperatorDep, request: Request, session: SessionDep) -> None:
    await record_audit(
        session,
        actor_id=operator.id,
        action="logout",
        resource_type="operator",
        resource_id=operator.id,
        ip_hash=hash_ip(client_ip(request)),
    )
    await session.commit()


@router.get("/me", response_model=OperatorOut)
async def me(operator: OperatorDep) -> Operator:
    return operator
