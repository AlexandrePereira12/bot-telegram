"""Comandos administrativos.

Uso:
    python -m app.cli create-admin --email admin@empresa.com [--password ...]
    python -m app.cli reset-2fa --email admin@empresa.com
    python -m app.cli seed-demo
    python -m app.cli list-tokens
"""

import argparse
import asyncio
import secrets
import sys

from app.core.database import SessionLocal
from app.core.enums import OperatorRole
from app.services.auth_service import (
    ROLES_REQUIRING_2FA,
    AuthError,
    create_operator,
    reset_totp,
)
from app.services.tracking_service import create_token


async def _create_admin(email: str, password: str | None, role: str) -> int:
    """Cria operador. Senha gerada quando nao informada — evita senha fraca
    escolhida no calor do setup e evita a senha aparecer no histórico do shell.
    """
    generated = password is None
    password = password or secrets.token_urlsafe(16)

    async with SessionLocal() as session:
        try:
            operator = await create_operator(
                session,
                email=email,
                password=password,
                role=OperatorRole(role),
            )
        except AuthError as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 1
        await session.commit()
        operator_id = operator.id

    print(f"operador criado: id={operator_id} email={email} role={role}")
    if generated:
        print(f"senha gerada: {password}")
        print("guarde agora — ela nao e recuperavel depois.")
    if OperatorRole(role) in ROLES_REQUIRING_2FA:
        print("\n  Este perfil exige 2FA. O cadastro do autenticador acontece")
        print("  no PRIMEIRO LOGIN pelo dashboard: entre com e-mail e senha e")
        print("  a tela mostra o QR para escanear.")
        print("  (o segredo nao e gerado aqui de proposito — assim ele nao")
        print("   circula por terminal, log ou historico antes do dono)")
    return 0


async def _reset_2fa(email: str) -> int:
    """Zera o cadastro do 2FA de um operador.

    Uso real: celular perdido ou trocado. Nao reexibe o segredo antigo — ele
    e descartado e o operador cadastra um novo no proximo login, pelo mesmo
    fluxo de QR do primeiro acesso.
    """
    from app.services.auth_service import get_operator_by_email

    async with SessionLocal() as session:
        operator = await get_operator_by_email(session, email)
        if operator is None:
            print(f"erro: operador {email} nao encontrado", file=sys.stderr)
            return 1
        if operator.role not in ROLES_REQUIRING_2FA:
            print(f"{email} (role={operator.role.value}) nao usa 2FA.")
            return 0

        reset_totp(operator)
        await session.commit()

    print(f"2FA de {email} reiniciado.")
    print("No proximo login (e-mail + senha) o dashboard mostra o QR novo.")
    return 0


async def _seed_demo() -> int:
    """Cria campanha e token de exemplo para testar o deep link."""
    from app.core.config import settings
    from app.models import Campaign

    async with SessionLocal() as session:
        campaign = Campaign(
            tenant_id=settings.tenant_id,
            name="Campanha de teste",
            source="meta",
            platform="meta_ads",
            external_id="demo-001",
        )
        session.add(campaign)
        await session.flush()
        token = await create_token(
            session, campaign_id=campaign.id, source="meta", label="criativo demo"
        )
        await session.commit()
        print(f"campanha criada: id={campaign.id}")
        print(f"tracking token: {token.token}")
        print(f"deep link: https://t.me/<seu_bot>?start={token.token}")
    return 0


async def _list_tokens() -> int:
    from sqlalchemy import select

    from app.core.config import settings
    from app.models import TrackingToken

    async with SessionLocal() as session:
        stmt = select(TrackingToken).where(TrackingToken.tenant_id == settings.tenant_id)
        for token in (await session.execute(stmt)).scalars():
            state = "revogado" if token.revoked_at else "ativo"
            print(f"{token.id}\t{token.token}\tcampanha={token.campaign_id}\t{state}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("create-admin", help="cria um operador")
    admin.add_argument("--email", required=True)
    admin.add_argument("--password", default=None)
    admin.add_argument(
        "--role", default=OperatorRole.ADMIN.value, choices=[r.value for r in OperatorRole]
    )

    show = sub.add_parser("reset-2fa", help="reinicia o 2FA (celular perdido)")
    show.add_argument("--email", required=True)

    sub.add_parser("seed-demo", help="cria campanha e tracking token de teste")
    sub.add_parser("list-tokens", help="lista tracking tokens")

    args = parser.parse_args()

    if args.command == "create-admin":
        code = asyncio.run(_create_admin(args.email, args.password, args.role))
    elif args.command == "reset-2fa":
        code = asyncio.run(_reset_2fa(args.email))
    elif args.command == "seed-demo":
        code = asyncio.run(_seed_demo())
    else:
        code = asyncio.run(_list_tokens())
    sys.exit(code)


if __name__ == "__main__":
    main()
