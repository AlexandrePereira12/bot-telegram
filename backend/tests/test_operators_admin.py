"""Cadastro de operadores pelo dashboard.

Rota privilegiada: as garantias testadas aqui sao a autorizacao (so ADMIN),
o isolamento por tenant e o sigilo da senha gerada.
"""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import OperatorRole
from app.core.security import create_access_token
from app.models import AuditLog, Operator
from app.services.auth_service import AuthError, create_operator

SENHA = "senha-de-teste-1234"


async def _operador(session: AsyncSession, role: OperatorRole, email: str) -> Operator:
    operator = await create_operator(session, email=email, password=SENHA, role=role)
    await session.flush()
    return operator


@pytest.fixture
def client(session: AsyncSession):
    """Cliente HTTP com a sessao do teste injetada no lugar da real."""
    from app.core.database import get_session
    from app.main import app

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


def _auth(operator: Operator) -> dict[str, str]:
    token = create_access_token(operator.id, operator.role.value)
    return {"Authorization": f"Bearer {token}"}


async def test_admin_cadastra_operador_com_perfil_escolhido(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.post(
            "/api/v1/operators",
            json={"email": "novo@teste.com", "full_name": "Novo", "role": "SUPPORT"},
            headers=_auth(admin),
        )

    assert response.status_code == 201
    corpo = response.json()
    assert corpo["email"] == "novo@teste.com"
    assert corpo["role"] == "SUPPORT"
    assert corpo["is_active"] is True
    # Sem senha no corpo do pedido, o servidor gera e devolve uma unica vez.
    assert corpo["generated_password"]


async def test_senha_informada_nao_e_devolvida(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.post(
            "/api/v1/operators",
            json={"email": "comsenha@teste.com", "role": "ANALYST", "password": SENHA},
            headers=_auth(admin),
        )

    assert response.status_code == 201
    assert response.json()["generated_password"] is None


@pytest.mark.parametrize(
    "role",
    [
        OperatorRole.MANAGER,
        OperatorRole.ANALYST,
        OperatorRole.OPERATOR,
        OperatorRole.SUPPORT,
    ],
)
async def test_perfil_nao_admin_nao_cadastra_nem_lista(
    session: AsyncSession, client: httpx.AsyncClient, role: OperatorRole
):
    outro = await _operador(session, role, f"{role.value.lower()}@teste.com")

    async with client:
        criacao = await client.post(
            "/api/v1/operators",
            json={"email": "invasor@teste.com", "role": "ADMIN"},
            headers=_auth(outro),
        )
        listagem = await client.get("/api/v1/operators", headers=_auth(outro))

    assert criacao.status_code == 403
    assert listagem.status_code == 403


async def test_sem_token_nao_acessa(session: AsyncSession, client: httpx.AsyncClient):
    async with client:
        response = await client.get("/api/v1/operators")
    assert response.status_code == 401


async def test_email_duplicado_responde_409(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        primeiro = await client.post(
            "/api/v1/operators",
            json={"email": "repetido@teste.com", "role": "SUPPORT"},
            headers=_auth(admin),
        )
        segundo = await client.post(
            "/api/v1/operators",
            json={"email": "REPETIDO@teste.com", "role": "ANALYST"},
            headers=_auth(admin),
        )

    assert primeiro.status_code == 201
    # E-mail e comparado sem diferenciar caixa: o duplicado nao passa.
    assert segundo.status_code == 409


async def test_listagem_nao_vaza_outro_tenant(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    session.add(
        Operator(
            tenant_id="outro-tenant",
            email="alheio@teste.com",
            password_hash="x",
            role=OperatorRole.ADMIN,
        )
    )
    await session.flush()

    async with client:
        response = await client.get("/api/v1/operators", headers=_auth(admin))

    assert response.status_code == 200
    emails = {linha["email"] for linha in response.json()}
    assert "alheio@teste.com" not in emails
    assert "admin@teste.com" in emails


async def test_senha_gerada_nao_aparece_na_auditoria(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.post(
            "/api/v1/operators",
            json={"email": "auditado@teste.com", "role": "OPERATOR"},
            headers=_auth(admin),
        )
    senha = response.json()["generated_password"]

    registros = (
        (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "operator", AuditLog.action == "create"
                )
            )
        )
        .scalars()
        .all()
    )
    assert registros, "cadastro precisa deixar rastro de auditoria"
    for registro in registros:
        assert senha not in str(registro.audit_metadata)
        assert registro.actor_id == admin.id


async def test_totp_pending_indica_admin_sem_autenticador(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.get("/api/v1/operators", headers=_auth(admin))

    linha = next(item for item in response.json() if item["email"] == "admin@teste.com")
    assert linha["totp_pending"] is True
    assert settings.tenant_id


async def test_payload_do_painel_com_campos_nulos_e_aceito(
    session: AsyncSession, client: httpx.AsyncClient
):
    """O formulário envia `null` explícito em nome e senha, não campo ausente.

    Constraint de tamanho em campo opcional é justamente onde `null` costuma
    virar 422 — e este é o caminho padrão da tela, o de senha gerada.
    """
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.post(
            "/api/v1/operators",
            json={
                "email": "doformulario@teste.com",
                "full_name": None,
                "role": "OPERATOR",
                "password": None,
            },
            headers=_auth(admin),
        )

    assert response.status_code == 201, response.text
    corpo = response.json()
    assert corpo["full_name"] is None
    assert corpo["generated_password"]


async def test_senha_curta_e_recusada(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.post(
            "/api/v1/operators",
            json={"email": "curta@teste.com", "role": "SUPPORT", "password": "1234"},
            headers=_auth(admin),
        )

    assert response.status_code == 422


# ------------------------------------------------- edicao, exclusao e 2FA


async def test_admin_edita_perfil_e_nome_de_outro(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alvo = await _operador(session, OperatorRole.SUPPORT, "alvo@teste.com")

    async with client:
        response = await client.patch(
            f"/api/v1/operators/{alvo.id}",
            json={"role": "MANAGER", "full_name": "Nome Novo"},
            headers=_auth(admin),
        )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "MANAGER"
    assert response.json()["full_name"] == "Nome Novo"


async def test_desativar_corta_o_acesso(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alvo = await _operador(session, OperatorRole.MANAGER, "alvo@teste.com")

    async with client:
        patch = await client.patch(
            f"/api/v1/operators/{alvo.id}",
            json={"is_active": False},
            headers=_auth(admin),
        )
        # O papel e relido do banco a cada requisicao: o token do desativado
        # deixa de valer na hora, sem esperar expirar.
        depois = await client.get("/api/v1/leads", headers=_auth(alvo))

    assert patch.status_code == 200
    assert patch.json()["is_active"] is False
    assert depois.status_code == 401


async def test_admin_nao_rebaixa_a_si_mesmo(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    await _operador(session, OperatorRole.ADMIN, "outro@teste.com")

    async with client:
        response = await client.patch(
            f"/api/v1/operators/{admin.id}",
            json={"role": "ANALYST"},
            headers=_auth(admin),
        )

    assert response.status_code == 409
    await session.refresh(admin)
    assert admin.role is OperatorRole.ADMIN


async def test_admin_nao_se_desativa(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    await _operador(session, OperatorRole.ADMIN, "outro@teste.com")

    async with client:
        response = await client.patch(
            f"/api/v1/operators/{admin.id}",
            json={"is_active": False},
            headers=_auth(admin),
        )

    assert response.status_code == 409
    await session.refresh(admin)
    assert admin.is_active is True


async def test_admin_edita_o_proprio_nome(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        response = await client.patch(
            f"/api/v1/operators/{admin.id}",
            json={"full_name": "Ana Martins"},
            headers=_auth(admin),
        )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Ana Martins"


async def test_rebaixar_outro_admin_e_permitido_enquanto_sobrar_um(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    outro = await _operador(session, OperatorRole.ADMIN, "outro@teste.com")

    async with client:
        response = await client.patch(
            f"/api/v1/operators/{outro.id}", json={"role": "ANALYST"}, headers=_auth(admin)
        )

    assert response.status_code == 200
    assert response.json()["role"] == "ANALYST"


async def test_guarda_do_ultimo_admin(session: AsyncSession):
    """Testado no servico, nao na rota.

    Pela API o caso e inalcancavel hoje: quem chama ja e um ADMIN ativo, e
    mexer na propria conta cai antes no guarda de acao sobre si mesmo. O
    guarda existe para o dia em que `admin:write` for concedido a outro
    perfil — e e aqui que ele pode ser exercitado.
    """
    from app.services.auth_service import count_active_admins, ensure_admin_remains

    unico = await _operador(session, OperatorRole.ADMIN, "unico@teste.com")
    suporte = await _operador(session, OperatorRole.SUPPORT, "suporte@teste.com")

    assert await count_active_admins(session) == 1
    # Tirar o suporte nao ameaca nada.
    await ensure_admin_remains(session, excluding=suporte.id)

    with pytest.raises(AuthError):
        await ensure_admin_remains(session, excluding=unico.id)

    segundo = await _operador(session, OperatorRole.ADMIN, "segundo@teste.com")
    assert await count_active_admins(session) == 2
    # Com dois, tirar um deixa de ser problema.
    await ensure_admin_remains(session, excluding=segundo.id)


async def test_admin_inativo_nao_conta_como_ultimo_admin(session: AsyncSession):
    from app.services.auth_service import count_active_admins

    ativo = await _operador(session, OperatorRole.ADMIN, "ativo@teste.com")
    inativo = await _operador(session, OperatorRole.ADMIN, "inativo@teste.com")
    inativo.is_active = False
    await session.flush()

    assert await count_active_admins(session) == 1
    assert await count_active_admins(session, excluding=ativo.id) == 0


async def test_excluir_admin_inativo_e_permitido(
    session: AsyncSession, client: httpx.AsyncClient
):
    """O guarda protege o ultimo ADMIN *ativo*: quem ja esta desativado nao
    sustenta o acesso da instalacao e pode sair."""
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    outro = await _operador(session, OperatorRole.ADMIN, "outro@teste.com")
    outro.is_active = False
    await session.flush()

    async with client:
        response = await client.delete(f"/api/v1/operators/{outro.id}", headers=_auth(admin))

    assert response.status_code == 204


async def test_exclusao_de_quem_tem_historico_e_recusada(
    session: AsyncSession, client: httpx.AsyncClient
):
    from app.services.event_service import record_audit

    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alvo = await _operador(session, OperatorRole.OPERATOR, "comhistorico@teste.com")
    await record_audit(
        session, actor_id=alvo.id, action="login", resource_type="operator", resource_id=alvo.id
    )
    await session.flush()

    async with client:
        response = await client.delete(f"/api/v1/operators/{alvo.id}", headers=_auth(admin))

    assert response.status_code == 409
    assert "desative" in response.json()["detail"]
    # A linha continua la: auditoria nao perde o autor.
    assert await session.get(Operator, alvo.id) is not None


async def test_exclusao_de_usuario_sem_historico(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alvo = await _operador(session, OperatorRole.SUPPORT, "novinho@teste.com")
    alvo_id = alvo.id

    async with client:
        response = await client.delete(f"/api/v1/operators/{alvo_id}", headers=_auth(admin))

    assert response.status_code == 204
    assert await session.get(Operator, alvo_id) is None


async def test_admin_nao_exclui_a_si_mesmo(session: AsyncSession, client: httpx.AsyncClient):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    await _operador(session, OperatorRole.ADMIN, "outro@teste.com")

    async with client:
        response = await client.delete(f"/api/v1/operators/{admin.id}", headers=_auth(admin))

    assert response.status_code == 409
    assert await session.get(Operator, admin.id) is not None


async def test_reset_2fa_devolve_o_operador_ao_estado_pendente(
    session: AsyncSession, client: httpx.AsyncClient
):
    import pyotp

    from app.services.auth_service import confirm_enrollment, start_enrollment

    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alvo = await _operador(session, OperatorRole.ADMIN, "perdeuocelular@teste.com")
    start_enrollment(alvo)
    confirm_enrollment(alvo, pyotp.TOTP(alvo.totp_secret).now())
    await session.flush()
    assert alvo.totp_pending is False

    async with client:
        response = await client.post(
            f"/api/v1/operators/{alvo.id}/reset-2fa", headers=_auth(admin)
        )

    assert response.status_code == 200
    assert response.json()["totp_pending"] is True
    await session.refresh(alvo)
    assert alvo.totp_secret is None


async def test_reset_2fa_em_perfil_sem_2fa_e_recusado(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alvo = await _operador(session, OperatorRole.SUPPORT, "suporte@teste.com")

    async with client:
        response = await client.post(
            f"/api/v1/operators/{alvo.id}/reset-2fa", headers=_auth(admin)
        )

    assert response.status_code == 409


async def test_operador_inexistente_responde_404(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")

    async with client:
        patch = await client.patch(
            "/api/v1/operators/999999", json={"full_name": "x"}, headers=_auth(admin)
        )
        remocao = await client.delete("/api/v1/operators/999999", headers=_auth(admin))

    assert patch.status_code == 404
    assert remocao.status_code == 404


async def test_operador_de_outro_tenant_responde_404(
    session: AsyncSession, client: httpx.AsyncClient
):
    admin = await _operador(session, OperatorRole.ADMIN, "admin@teste.com")
    alheio = Operator(
        tenant_id="outro-tenant",
        email="alheio@teste.com",
        password_hash="x",
        role=OperatorRole.SUPPORT,
    )
    session.add(alheio)
    await session.flush()

    async with client:
        response = await client.patch(
            f"/api/v1/operators/{alheio.id}", json={"role": "ADMIN"}, headers=_auth(admin)
        )

    assert response.status_code == 404


@pytest.mark.parametrize("metodo", ["patch", "delete"])
async def test_perfil_nao_admin_nao_edita_nem_exclui(
    session: AsyncSession, client: httpx.AsyncClient, metodo: str
):
    manager = await _operador(session, OperatorRole.MANAGER, "manager@teste.com")
    alvo = await _operador(session, OperatorRole.SUPPORT, "alvo@teste.com")

    async with client:
        if metodo == "patch":
            response = await client.patch(
                f"/api/v1/operators/{alvo.id}", json={"role": "ADMIN"}, headers=_auth(manager)
            )
        else:
            response = await client.delete(
                f"/api/v1/operators/{alvo.id}", headers=_auth(manager)
            )

    assert response.status_code == 403
