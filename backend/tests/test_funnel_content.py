"""Conteudo do funil por campanha, fallback e compliance na escrita."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import FunnelStep, OptionTarget
from app.models import Campaign, FunnelContent, QualificationOption
from app.services import content_service
from app.services.compliance import ComplianceError, assert_compliant, find_violations


async def _outra_campanha(session: AsyncSession) -> Campaign:
    c = Campaign(
        tenant_id=settings.tenant_id, name="Outra", source="google", external_id="c2"
    )
    session.add(c)
    await session.flush()
    return c


# ------------------------------------------------------------------- fallback
async def test_sem_nada_no_banco_usa_o_texto_do_codigo(session: AsyncSession):
    """Apagar o conteudo global nao pode deixar o bot mudo."""
    resolved = await content_service.get_content(session, FunnelStep.WELCOME, None)
    assert "Bem-vindo" in resolved.body


async def test_campanha_sem_texto_proprio_usa_o_global(
    session: AsyncSession, campaign, global_content
):
    resolved = await content_service.get_content(session, FunnelStep.WELCOME, campaign.id)
    assert resolved.body == "Ola{name}! Bem-vindo(a) a {company}."


async def test_texto_da_campanha_vence_o_global(
    session: AsyncSession, campaign, global_content
):
    session.add(
        FunnelContent(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            step=FunnelStep.WELCOME,
            body="Texto exclusivo da campanha",
        )
    )
    await session.flush()

    da_campanha = await content_service.get_content(session, FunnelStep.WELCOME, campaign.id)
    global_ = await content_service.get_content(session, FunnelStep.WELCOME, None)

    assert da_campanha.body == "Texto exclusivo da campanha"
    assert global_.body != da_campanha.body, "o global segue intacto"


async def test_campanhas_diferentes_recebem_textos_diferentes(
    session: AsyncSession, campaign, global_content
):
    outra = await _outra_campanha(session)
    session.add_all(
        [
            FunnelContent(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                step=FunnelStep.WELCOME,
                body="Bem-vindo da campanha A",
            ),
            FunnelContent(
                tenant_id=settings.tenant_id,
                campaign_id=outra.id,
                step=FunnelStep.WELCOME,
                body="Bem-vindo da campanha B",
            ),
        ]
    )
    await session.flush()

    a = await content_service.get_content(session, FunnelStep.WELCOME, campaign.id)
    b = await content_service.get_content(session, FunnelStep.WELCOME, outra.id)
    assert a.body == "Bem-vindo da campanha A"
    assert b.body == "Bem-vindo da campanha B"


async def test_etapa_de_efeito_legal_ignora_override_da_campanha(
    session: AsyncSession, campaign, global_content
):
    """Consentimento e age gate valem o texto global mesmo com linha propria."""
    session.add(
        FunnelContent(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            step=FunnelStep.CONSENT,
            body="Termos improvisados da campanha",
        )
    )
    await session.flush()

    resolved = await content_service.get_content(session, FunnelStep.CONSENT, campaign.id)
    assert resolved.body == "Termos versao {version}. Voce aceita?"


# -------------------------------------------------------------------- render
async def test_render_preenche_variaveis(session: AsyncSession, global_content):
    resolved = await content_service.get_content(session, FunnelStep.WELCOME, None)
    texto = content_service.render(resolved.body, name=", Alexandre")
    assert texto == f", Alexandre! Bem-vindo(a) a {settings.company_name}.".replace(
        ", Alexandre!", "Ola, Alexandre!"
    )


def test_placeholder_invalido_nao_derruba_o_envio():
    """Texto digitado errado no painel mantem o corpo em vez de estourar."""
    assert content_service.render("Ola {nao_existe}") == "Ola {nao_existe}"


# -------------------------------------------------------------------- opcoes
async def test_opcoes_globais_quando_a_campanha_nao_tem(
    session: AsyncSession, campaign, global_content
):
    opcoes = await content_service.get_options(session, campaign.id)
    assert [o.key for o in opcoes] == ["service_info", "faq", "human_support"]


async def test_opcoes_da_campanha_substituem_as_globais(
    session: AsyncSession, campaign, global_content
):
    session.add(
        QualificationOption(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            key="quero_agora",
            label="Quero agora",
            target=OptionTarget.HUMAN_SUPPORT,
            sort_order=1,
        )
    )
    await session.flush()

    opcoes = await content_service.get_options(session, campaign.id)
    assert [o.key for o in opcoes] == ["quero_agora"], "nao mistura com as globais"
    assert opcoes[0].target == OptionTarget.HUMAN_SUPPORT


async def test_opcao_desativada_some_do_teclado(
    session: AsyncSession, campaign, global_content
):
    stmt_options = await content_service.get_options(session, None)
    assert len(stmt_options) == 3

    from sqlalchemy import select

    faq = (
        await session.execute(
            select(QualificationOption).where(QualificationOption.key == "faq")
        )
    ).scalar_one()
    faq.is_active = False
    await session.flush()

    opcoes = await content_service.get_options(session, None)
    assert [o.key for o in opcoes] == ["service_info", "human_support"]


async def test_opcao_inexistente_nao_resolve(session: AsyncSession, global_content):
    assert await content_service.resolve_option(session, None, "inventada") is None
    assert await content_service.resolve_option(session, None, "faq") is not None


async def test_ordem_das_opcoes_respeita_sort_order(
    session: AsyncSession, campaign, global_content
):
    session.add_all(
        [
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="terceira",
                label="C",
                sort_order=30,
            ),
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="primeira",
                label="A",
                sort_order=10,
            ),
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="segunda",
                label="B",
                sort_order=20,
            ),
        ]
    )
    await session.flush()

    opcoes = await content_service.get_options(session, campaign.id)
    assert [o.key for o in opcoes] == ["primeira", "segunda", "terceira"]


# ---------------------------------------------------------------- compliance
@pytest.mark.parametrize(
    "texto",
    [
        "Ganho garantido para voce!",
        "GANHO GARANTIDO",
        "ganho  garantido",  # espaco duplicado
        "Gánho Garantído",  # com acento
        "Aqui e lucro certo",
        "Dinheiro facil todo dia",
        "Aposte agora e fique rico",
        "Investimento sem risco",
    ],
)
def test_texto_que_promete_ganho_e_recusado(texto: str):
    with pytest.raises(ComplianceError):
        assert_compliant(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Bem-vindo! Conheca nosso servico.",
        "Este conteudo e restrito a maiores de 18 anos.",
        "Voce entrou na fila de atendimento.",
        "Jogue com responsabilidade.",
    ],
)
def test_texto_normal_passa(texto: str):
    assert assert_compliant(texto) == texto


def test_violacao_informa_qual_termo():
    violacoes = find_violations("isso e lucro certo e sem risco")
    assert "lucro certo" in violacoes
    assert "sem risco" in violacoes


def test_texto_do_codigo_continua_limpo():
    """O fallback tambem precisa respeitar a regra."""
    from app.bot import texts

    for nome, valor in vars(texts).items():
        if isinstance(valor, str) and not nome.startswith("_"):
            assert not find_violations(valor), f"{nome} promete resultado"


# --------------------------------------------------- resposta por opcao
async def test_opcao_pode_ter_resposta_propria(session: AsyncSession, campaign):
    session.add(
        QualificationOption(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            key="precos",
            label="Ver precos",
            target=OptionTarget.INFORMATION,
            response_body="Nossos planos comecam em R$ 49/mes.",
        )
    )
    await session.flush()

    opcao = await content_service.resolve_option(session, campaign.id, "precos")
    resposta = opcao.response()
    assert resposta is not None
    assert resposta.body == "Nossos planos comecam em R$ 49/mes."


async def test_opcao_sem_resposta_cai_no_texto_generico(
    session: AsyncSession, campaign, global_content
):
    opcao = await content_service.resolve_option(session, campaign.id, "faq")
    assert opcao.response() is None, "sem resposta propria, usa o texto da etapa"


async def test_respostas_diferentes_por_opcao(session: AsyncSession, campaign):
    session.add_all(
        [
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="precos",
                label="Precos",
                response_body="Planos a partir de R$ 49.",
                sort_order=10,
            ),
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="suporte",
                label="Suporte",
                response_body="Atendemos de segunda a sexta, 9h as 18h.",
                sort_order=20,
            ),
        ]
    )
    await session.flush()

    precos = await content_service.resolve_option(session, campaign.id, "precos")
    suporte = await content_service.resolve_option(session, campaign.id, "suporte")
    assert precos.response().body != suporte.response().body


async def test_resposta_da_opcao_tambem_valida_compliance():
    """A resposta passa pelo mesmo filtro do texto das etapas."""
    with pytest.raises(ComplianceError):
        assert_compliant("Escolha essa opcao e tenha lucro certo")
