"""Configuracao da integracao de IA pelo painel.

A garantia central e simples de enunciar e facil de perder numa refatoracao: a
chave de API entra e nunca mais sai. Nem pela rota que a criou, nem pela que
lista, nem pela auditoria.
"""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import AiProvider, OperatorRole
from app.core.security import create_access_token, decrypt_secret
from app.models import AiIntegration, AuditLog, Operator
from app.services import ai_service
from app.services.auth_service import create_operator

SENHA = "senha-de-teste-1234"
CHAVE = "AIzaSyChaveFalsaParaTesteDeIntegracao123"


@pytest.fixture
def client(session: AsyncSession):
    from app.core.database import get_session
    from app.main import app

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


def _auth(operator: Operator) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(operator.id, operator.role.value)}"}


async def _admin(session: AsyncSession, email: str = "admin@teste.com") -> Operator:
    operator = await create_operator(
        session, email=email, password=SENHA, role=OperatorRole.ADMIN
    )
    await session.flush()
    return operator


async def test_admin_configura_e_a_chave_nao_volta(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _admin(session)

    async with client:
        criada = await client.put(
            "/api/v1/settings/ai",
            json={
                "provider": "GEMINI",
                "model": "gemini-2.5-flash",
                "api_key": CHAVE,
                "is_active": True,
            },
            headers=_auth(admin),
        )
        lida = await client.get("/api/v1/settings/ai", headers=_auth(admin))

    assert criada.status_code == 200
    corpo = criada.json()
    assert corpo["configured"] is True
    assert corpo["provider"] == "GEMINI"
    assert CHAVE not in criada.text, "a chave nunca volta na resposta"
    assert corpo["api_key_masked"].startswith("AIza")
    assert corpo["api_key_masked"].endswith("123")
    assert CHAVE not in lida.text

    linha = (await session.execute(select(AiIntegration))).scalar_one()
    assert linha.api_key_encrypted != CHAVE, "guardada cifrada"
    assert CHAVE not in linha.api_key_encrypted
    assert decrypt_secret(linha.api_key_encrypted) == CHAVE, "reversivel para uso"


async def test_auditoria_registra_a_decisao_sem_o_segredo(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _admin(session)

    async with client:
        await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "gemini-2.5-flash", "api_key": CHAVE},
            headers=_auth(admin),
        )

    registro = (
        await session.execute(
            select(AuditLog).where(AuditLog.resource_type == "ai_integration")
        )
    ).scalar_one()
    assert registro.audit_metadata["key_changed"] is True
    assert CHAVE not in str(registro.audit_metadata)


async def test_chave_vazia_mantem_a_atual(session: AsyncSession, client: httpx.AsyncClient):
    """Trocar modelo ou desativar nao pode exigir digitar o segredo de novo."""
    admin = await _admin(session)

    async with client:
        await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "gemini-2.5-flash", "api_key": CHAVE},
            headers=_auth(admin),
        )
        atualizada = await client.put(
            "/api/v1/settings/ai",
            json={
                "provider": "GEMINI",
                "model": "gemini-2.5-pro",
                "api_key": None,
                "is_active": False,
            },
            headers=_auth(admin),
        )

    assert atualizada.json()["model"] == "gemini-2.5-pro"
    assert atualizada.json()["is_active"] is False

    linha = (await session.execute(select(AiIntegration))).scalar_one()
    assert decrypt_secret(linha.api_key_encrypted) == CHAVE, "chave preservada"


async def test_primeira_configuracao_exige_a_chave(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _admin(session)

    async with client:
        resposta = await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "gemini-2.5-flash"},
            headers=_auth(admin),
        )

    assert resposta.status_code == 422
    assert (await session.execute(select(AiIntegration))).first() is None


@pytest.mark.parametrize(
    "role", [OperatorRole.MANAGER, OperatorRole.OPERATOR, OperatorRole.ANALYST]
)
async def test_so_admin_configura(
    session: AsyncSession, client: httpx.AsyncClient, role: OperatorRole
):
    """Chave de provedor e segredo da instalacao, nao conteudo de campanha."""
    operator = await create_operator(
        session, email=f"{role.value.lower()}@teste.com", password=SENHA, role=role
    )
    await session.flush()

    async with client:
        leitura = await client.get("/api/v1/settings/ai", headers=_auth(operator))
        escrita = await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "x", "api_key": CHAVE},
            headers=_auth(operator),
        )

    assert leitura.status_code == 403
    assert escrita.status_code == 403


async def test_sem_token_nao_acessa(session: AsyncSession, client: httpx.AsyncClient):
    async with client:
        assert (await client.get("/api/v1/settings/ai")).status_code == 401


async def test_remover_desliga_o_atendimento_por_ia(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _admin(session)

    async with client:
        await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "gemini-2.5-flash", "api_key": CHAVE},
            headers=_auth(admin),
        )
        assert await ai_service.disponivel(session) is True

        removida = await client.delete("/api/v1/settings/ai", headers=_auth(admin))

    assert removida.status_code == 204
    assert await ai_service.disponivel(session) is False


async def test_teste_de_conexao_guarda_o_resultado(
    session: AsyncSession, client: httpx.AsyncClient, monkeypatch
):
    """Erro de chave aparece aqui, e nao quando um lead ficar sem resposta."""
    admin = await _admin(session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "API key not valid"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda *a, **kw: original(transport=httpx.MockTransport(handler)),
    )

    async with client:
        await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "gemini-2.5-flash", "api_key": CHAVE},
            headers=_auth(admin),
        )
        resultado = await client.post("/api/v1/settings/ai/test", headers=_auth(admin))

    assert resultado.status_code == 200
    corpo = resultado.json()
    assert corpo["ok"] is False
    assert "chave invalida" in corpo["detail"]

    linha = (await session.execute(select(AiIntegration))).scalar_one()
    assert linha.last_checked_at is not None
    assert "401" in linha.last_error


async def test_teste_de_conexao_bem_sucedido(
    session: AsyncSession, client: httpx.AsyncClient, monkeypatch
):
    admin = await _admin(session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-goog-api-key") == CHAVE
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda *a, **kw: original(transport=httpx.MockTransport(handler)),
    )

    async with client:
        await client.put(
            "/api/v1/settings/ai",
            json={"provider": "GEMINI", "model": "gemini-2.5-flash", "api_key": CHAVE},
            headers=_auth(admin),
        )
        resultado = await client.post("/api/v1/settings/ai/test", headers=_auth(admin))

    assert resultado.json()["ok"] is True
    assert resultado.json()["sample"] == "ok"

    linha = (await session.execute(select(AiIntegration))).scalar_one()
    assert linha.last_error is None


async def test_integracao_de_outro_tenant_nao_e_usada(session: AsyncSession):
    """O isolamento vale tambem para segredo de integracao."""
    from app.core.security import encrypt_secret, mask_secret

    session.add(
        AiIntegration(
            tenant_id="outra-empresa",
            provider=AiProvider.GEMINI,
            api_key_encrypted=encrypt_secret(CHAVE),
            api_key_hint=mask_secret(CHAVE),
            model="gemini-2.5-flash",
            is_active=True,
        )
    )
    await session.flush()

    assert await ai_service.integracao_ativa(session) is None
    assert settings.tenant_id != "outra-empresa"
