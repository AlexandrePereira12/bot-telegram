"""Dependencias compartilhadas da API: sessao, operador autenticado, RBAC."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.redis_client import rate_limit_hit
from app.core.security import decode_token
from app.models import Operator
from app.services.auth_service import has_permission

bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def client_ip(request: Request) -> str:
    """IP da requisicao.

    X-Forwarded-For so e confiavel porque o unico caminho de entrada e o
    Nginx do proprio deployment, que reescreve o header.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_current_operator(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Operator:
    """Operador autenticado.

    O papel do JWT nunca e usado para autorizar: a linha do operador e
    relida do banco a cada requisicao, de modo que revogar acesso tenha
    efeito imediato, sem esperar o token expirar.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="nao autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials, "access")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token invalido"
        ) from exc

    operator = await session.get(Operator, int(payload["sub"]))
    if operator is None or not operator.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token invalido")
    return operator


OperatorDep = Annotated[Operator, Depends(get_current_operator)]


def require(permission: str) -> Callable[..., Coroutine[Any, Any, Operator]]:
    """Guarda de RBAC por permissao nomeada."""

    async def _guard(operator: OperatorDep) -> Operator:
        if not has_permission(operator.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"perfil sem permissao: {permission}",
            )
        return operator

    return _guard


async def rate_limit(request: Request, bucket: str, limit: int) -> None:
    if await rate_limit_hit(bucket, client_ip(request), limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="limite de requisicoes excedido",
        )
