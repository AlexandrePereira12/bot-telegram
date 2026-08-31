"""Atendimento por IA antes da fila humana.

A chamada ao provedor e dublada com `httpx.MockTransport` — nenhuma
dependencia nova e nenhum acesso de rede. O que se garante aqui e o que
quebraria em silencio: a IA falando por cima do operador, o lead preso na
maquina, promessa de ganho saindo para o Telegram, e a feature mudando o
comportamento de quem nao a ligou.
"""

from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import messages as message_handlers
from app.core.config import settings
from app.core.enums import (
    AiProvider,
    EventType,
    FunnelState,
    OperatorRole,
    OptionTarget,
    SenderType,
)
from app.core.security import encrypt_secret, mask_secret
from app.models import AiIntegration, Event, TelegramUser
from app.models import Message as MessageRow
from app.services import ai_service, conversation_service, funnel_service, lead_service
from app.services.auth_service import create_operator
from app.services.tracking_service import ORGANIC


# --------------------------------------------------------------------- dublês
@dataclass
class FakeUser:
    id: int = 8001
    username: str | None = "lead"
    first_name: str | None = "Lead"
    language_code: str | None = "pt-br"


@dataclass
class FakeSent:
    message_id: int = 1


@dataclass
class FakeChat:
    id: int = 8001


@dataclass
class FakeBot:
    acoes: list[str] = field(default_factory=list)

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        self.acoes.append(action)


@dataclass
class FakeMessage:
    text: str | None = "oi"
    from_user: FakeUser = field(default_factory=FakeUser)
    chat: FakeChat = field(default_factory=FakeChat)
    message_id: int = 1
    caption: str | None = None
    content_type: str = "text"
    answers: list[str] = field(default_factory=list)
    photo: list | None = None
    video: object | None = None
    voice: object | None = None
    audio: object | None = None
    document: object | None = None
    bot: FakeBot = field(default_factory=FakeBot)

    async def answer(self, text: str, reply_markup=None) -> FakeSent:
        self.answers.append(text)
        return FakeSent(message_id=len(self.answers))


@pytest_asyncio.fixture
async def ia_ligada(session: AsyncSession):
    """Integracao ativa no banco — e ela que liga a funcionalidade.

    Sem esta linha o atendimento por IA nao existe, que e exatamente o que
    `test_sem_integracao_nao_atende` verifica do outro lado.
    """
    return await _integracao(session, AiProvider.GEMINI, "gemini-2.5-flash")


async def _integracao(
    session: AsyncSession, provider: AiProvider, model: str, ativa: bool = True
) -> AiIntegration:
    integracao = AiIntegration(
        tenant_id=settings.tenant_id,
        provider=provider,
        api_key_encrypted=encrypt_secret("chave-de-teste-do-provedor"),
        api_key_hint=mask_secret("chave-de-teste-do-provedor"),
        model=model,
        is_active=ativa,
    )
    session.add(integracao)
    await session.flush()
    return integracao


def _responde(texto: str, status: int = 200):
    """Dublê do provedor.

    Responde no formato certo para cada um: o Gemini devolve `candidates` com
    `parts`, o OpenRouter devolve `choices`. A URL diz qual e.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "cota"}})
        if "generativelanguage" in str(request.url):
            return httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]}
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": texto}}]}
        )

    return handler


@pytest.fixture
def provedor(monkeypatch):
    """Substitui o cliente HTTP do serviço por um transporte de teste."""

    def instalar(handler, **kwargs):
        transporte = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def fabrica(*args, **client_kwargs):
            client_kwargs.pop("timeout", None)
            return original(transport=transporte, **client_kwargs)

        monkeypatch.setattr(ai_service.httpx, "AsyncClient", fabrica)

    return instalar


async def _lead_em_atendimento(session: AsyncSession, telegram_id: int = 8001):
    """Lead que percorreu o funil e escolheu falar com o time."""
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=telegram_id, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)
    await funnel_service.transition(session, user, FunnelState.AI_SUPPORT, lead=lead)
    await session.flush()
    return user, lead


async def _mensagens_da_ia(session: AsyncSession) -> list[MessageRow]:
    return list(
        (
            await session.execute(
                select(MessageRow).where(MessageRow.sender_type == SenderType.AI)
            )
        ).scalars()
    )


async def _pedidos(session: AsyncSession) -> int:
    """Pedidos de humano feitos durante o atendimento por IA."""
    return await session.scalar(
        select(func.count(Event.id)).where(
            Event.event_type == EventType.AI_HANDOFF_REQUESTED
        )
    )


# ------------------------------------------------------------------ caminho feliz
async def test_ia_responde_e_registra(session: AsyncSession, ia_ligada, provedor):
    provedor(_responde("A rodada termina quando o aviao vai embora."))
    user, lead = await _lead_em_atendimento(session)

    message = FakeMessage(text="como funciona o multiplicador?")
    await message_handlers.on_message(message, session)

    assert message.answers == ["A rodada termina quando o aviao vai embora."]
    assert message.bot.acoes == ["typing"], "indicador de digitacao antes da resposta"

    gravadas = await _mensagens_da_ia(session)
    assert len(gravadas) == 1
    assert gravadas[0].content == "A rodada termina quando o aviao vai embora."

    eventos = [e.event_type for e in (await session.execute(select(Event))).scalars()]
    assert EventType.AI_REPLIED in eventos


async def test_material_da_campanha_entra_no_prompt(
    session: AsyncSession, ia_ligada, provedor, campaign, global_content
):
    """O que a IA sabe sobre a operacao vem do conteudo cadastrado."""
    from app.core.config import settings as cfg
    from app.models import QualificationOption

    session.add(
        QualificationOption(
            tenant_id=cfg.tenant_id,
            campaign_id=None,
            key="saques",
            label="Saques",
            target=OptionTarget.INFORMATION,
            response_body="O saque sai pelo Pix da mesma titularidade.",
        )
    )
    await session.flush()

    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        capturado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provedor(handler)
    user, lead = await _lead_em_atendimento(session)
    await message_handlers.on_message(FakeMessage(text="como saco?"), session)

    system = capturado["systemInstruction"]["parts"][0]["text"]
    assert "mesma titularidade" in system, "resposta cadastrada vira base do prompt"
    # A pergunta desta rodada precisa ser o ultimo turno: sem esta assercao, a
    # IA poderia estar respondendo a mensagem anterior e o dublê nao acusaria.
    ultimo = capturado["contents"][-1]
    assert ultimo["role"] == "user"
    assert ultimo["parts"][0]["text"] == "como saco?"


# ------------------------------------------------------------- limite da IA
async def test_operador_atribuido_silencia_a_ia(
    session: AsyncSession, ia_ligada, provedor
):
    """Com operador na conversa, a IA nao fala por cima dele."""
    provedor(_responde("nao deveria sair"))
    user, lead = await _lead_em_atendimento(session)
    operator = await create_operator(
        session, email="op-ia@teste.com", password="senha-de-teste-1234",
        role=OperatorRole.OPERATOR,
    )
    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.assign(session, conversation.id, operator)
    await session.flush()

    message = FakeMessage(text="oi, tem alguem ai?")
    await message_handlers.on_message(message, session)

    assert message.answers == [], "nenhuma resposta automatica"
    assert await _mensagens_da_ia(session) == []


async def test_primeiro_pedido_mantem_a_ia_e_o_segundo_escala(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """Insistencia e o unico gatilho de escalada — um pedido nao basta."""
    provedor(_responde("posso ajudar por aqui"))
    user, lead = await _lead_em_atendimento(session)
    assert await _pedidos(session) == 0

    primeira = FakeMessage(text="quero falar com um atendente")
    await message_handlers.on_message(primeira, session)
    assert await _pedidos(session) == 1
    assert user.current_state == FunnelState.AI_SUPPORT, "a IA continua atendendo"
    assert len(await _mensagens_da_ia(session)) == 1

    segunda = FakeMessage(text="falar com uma pessoa, por favor")
    await message_handlers.on_message(segunda, session)
    assert await _pedidos(session) == 2
    assert user.current_state == FunnelState.HUMAN_SUPPORT, "escalou na insistencia"
    assert len(await _mensagens_da_ia(session)) == 1, "a IA nao respondeu de novo"


async def test_apos_escalar_a_ia_nao_volta(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    provedor(_responde("resposta"))
    user, lead = await _lead_em_atendimento(session)
    await funnel_service.transition(
        session, user, FunnelState.HUMAN_SUPPORT, lead=lead
    )
    await session.flush()

    message = FakeMessage(text="e ai?")
    await message_handlers.on_message(message, session)

    assert await _mensagens_da_ia(session) == []
    assert "atendimento" in message.answers[-1].lower()


# ------------------------------------------------------------------- falhas
async def test_cota_estourada_manda_para_a_fila(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """429 e o erro mais comum de modelo gratuito: nao pode prender o lead."""
    provedor(_responde("", status=429))
    user, lead = await _lead_em_atendimento(session)

    message = FakeMessage(text="oi")
    await message_handlers.on_message(message, session)

    assert await _mensagens_da_ia(session) == [], "nada gerado"
    assert len(message.answers) == 2, "aviso + mensagem da fila"
    assert user.current_state == FunnelState.HUMAN_SUPPORT

    eventos = [e.event_type for e in (await session.execute(select(Event))).scalars()]
    assert EventType.AI_FAILED in eventos


async def test_resposta_com_promessa_de_ganho_nao_sai(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """A saida da IA passa pela mesma validacao da API."""
    provedor(_responde("Com essa estrategia o lucro garantido e seu!"))
    user, lead = await _lead_em_atendimento(session)

    message = FakeMessage(text="tem alguma estrategia?")
    await message_handlers.on_message(message, session)

    assert await _mensagens_da_ia(session) == []
    assert all("lucro garantido" not in t for t in message.answers)

    falhas = [
        e
        for e in (await session.execute(select(Event))).scalars()
        if e.event_type == EventType.AI_FAILED
    ]
    assert falhas and falhas[-1].event_metadata["reason"] == "compliance"


async def test_sem_integracao_nao_atende(
    session: AsyncSession, provedor, global_content
):
    """Sem integracao cadastrada, pedir atendimento vai direto para a fila."""
    provedor(_responde("nao deveria ser chamada"))
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8009, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)

    from app.services.content_service import ResolvedOption

    opcao = ResolvedOption(
        key="falar", label="Falar com atendente", target=OptionTarget.HUMAN_SUPPORT
    )
    await funnel_service.select_interest(session, user, lead, opcao)
    await session.flush()

    assert user.current_state == FunnelState.HUMAN_SUPPORT, "sem passar pela IA"

    message = FakeMessage(text="oi", from_user=FakeUser(id=8009))
    await message_handlers.on_message(message, session)
    assert await _mensagens_da_ia(session) == []


# --------------------------------------------------------- deteccao de pedido
@pytest.mark.parametrize(
    "texto",
    [
        "quero falar com um atendente",
        "me transfere pra uma pessoa",
        "FALAR COM ALGUEM",
        "isso aqui é um robô?",
    ],
)
def test_pedido_de_humano_reconhecido(texto: str):
    assert ai_service.pede_humano(texto)


@pytest.mark.parametrize(
    "texto", ["como funciona o cash out?", "qual o horario de saque", "", None]
)
def test_conversa_normal_nao_conta_como_pedido(texto: str | None):
    assert not ai_service.pede_humano(texto)


async def test_usuario_bloqueado_nao_aciona_a_ia(
    session: AsyncSession, ia_ligada, provedor
):
    provedor(_responde("nao deveria sair"))
    user, lead = await _lead_em_atendimento(session, telegram_id=8010)
    user.is_blocked = True
    await session.flush()

    message = FakeMessage(text="oi", from_user=FakeUser(id=8010))
    await message_handlers.on_message(message, session)

    assert message.answers == []
    assert await _mensagens_da_ia(session) == []


async def test_usuario_sem_lead_nao_quebra(session: AsyncSession, ia_ligada, provedor):
    """Estado de atendimento sem lead associado nao pode derrubar o handler."""
    provedor(_responde("tudo certo"))
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8011, first_name="Sem lead"
    )
    user.current_state = FunnelState.AI_SUPPORT
    await session.flush()

    message = FakeMessage(text="oi", from_user=FakeUser(id=8011))
    await message_handlers.on_message(message, session)

    assert message.answers == ["tudo certo"]


async def test_lead_desconhecido_no_estado_da_ia(session: AsyncSession):
    """Sanidade: `TelegramUser` novo comeca fora do atendimento por IA."""
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8012, first_name="Novo"
    )
    assert FunnelState(user.current_state) != FunnelState.AI_SUPPORT
    assert (
        await session.scalar(
            select(func.count(TelegramUser.id)).where(TelegramUser.telegram_id == 8012)
        )
        == 1
    )


async def test_entrada_pelo_menu_nao_conta_como_insistencia(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """Escolher "falar com atendente" leva a IA, e ela responde a primeira vez.

    Se a porta de entrada contasse como pedido, o limiar cairia para um unico
    pedido dentro do chat — e a IA sairia de cena antes de tentar ajudar.
    """
    from app.services.content_service import ResolvedOption

    provedor(_responde("claro, me conta o que aconteceu"))
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8020, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)

    opcao = ResolvedOption(
        key="falar", label="Falar com atendente", target=OptionTarget.HUMAN_SUPPORT
    )
    await funnel_service.select_interest(session, user, lead, opcao)
    await session.flush()

    assert user.current_state == FunnelState.AI_SUPPORT, "entrou na IA, nao na fila"
    assert await _pedidos(session) == 0, "a entrada nao conta como insistencia"

    message = FakeMessage(text="meu saque nao caiu", from_user=FakeUser(id=8020))
    await message_handlers.on_message(message, session)

    assert len(await _mensagens_da_ia(session)) == 1, "a IA respondeu"
    assert user.current_state == FunnelState.AI_SUPPORT


async def test_reabertura_nao_herda_pedidos_do_ciclo_anterior(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """Ciclo novo comeca do zero — senao a IA escalaria no primeiro pedido.

    O corte e o ultimo `AI_SUPPORT_STARTED`, e nao o `started_at` da conversa:
    reabrir um atendimento mantem o `started_at` original, e os pedidos do
    ciclo anterior continuariam contando.
    """
    from app.services.content_service import ResolvedOption

    provedor(_responde("posso ajudar"))
    opcao = ResolvedOption(
        key="falar", label="Falar com atendente", target=OptionTarget.HUMAN_SUPPORT
    )

    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8030, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)

    # Ciclo 1: entra na IA e insiste ate escalar.
    await funnel_service.select_interest(session, user, lead, opcao)
    await session.flush()
    for _ in range(2):
        await message_handlers.on_message(
            FakeMessage(text="quero falar com uma pessoa", from_user=FakeUser(id=8030)),
            session,
        )
    assert user.current_state == FunnelState.HUMAN_SUPPORT
    assert await _pedidos(session) == 2

    # Ciclo 2: volta para a IA por uma escolha nova no menu.
    await funnel_service.transition(session, user, FunnelState.INFORMATION, lead=lead)
    await funnel_service.select_interest(session, user, lead, opcao)
    await session.flush()
    assert user.current_state == FunnelState.AI_SUPPORT

    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    assert await ai_service.pedidos_de_humano(session, user, conversation) == 0

    antes = len(await _mensagens_da_ia(session))
    await message_handlers.on_message(
        FakeMessage(text="e sobre o saque?", from_user=FakeUser(id=8030)), session
    )
    assert len(await _mensagens_da_ia(session)) == antes + 1, "a IA atende de novo"
    assert user.current_state == FunnelState.AI_SUPPORT


async def test_entrada_na_ia_gera_evento_de_inicio(
    session: AsyncSession, ia_ligada, global_content
):
    """`AI_SUPPORT_STARTED` alimenta a metrica e o corte do contador."""
    from app.services.content_service import ResolvedOption

    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8031, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)
    await funnel_service.select_interest(
        session,
        user,
        lead,
        ResolvedOption(key="falar", label="Falar", target=OptionTarget.HUMAN_SUPPORT),
    )
    await session.flush()

    eventos = [e.event_type for e in (await session.execute(select(Event))).scalars()]
    assert EventType.AI_SUPPORT_STARTED in eventos


async def test_integracao_inativa_nao_atende(
    session: AsyncSession, provedor, global_content
):
    """Desligar no painel tem efeito imediato — sem cache no caminho."""
    provedor(_responde("nao deveria sair"))
    await _integracao(session, AiProvider.GEMINI, "gemini-2.5-flash", ativa=False)
    user, lead = await _lead_em_atendimento(session, telegram_id=8040)

    message = FakeMessage(text="oi", from_user=FakeUser(id=8040))
    await message_handlers.on_message(message, session)

    assert await _mensagens_da_ia(session) == []


async def test_openrouter_usa_o_formato_de_chat_completions(
    session: AsyncSession, provedor, global_content
):
    """Cada provedor tem seu formato; trocar no painel nao pode quebrar o envio."""
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        capturado["url"] = str(request.url)
        capturado["auth"] = request.headers.get("authorization")
        capturado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provedor(handler)
    await _integracao(session, AiProvider.OPENROUTER, "google/gemma-4-31b-it:free")
    user, lead = await _lead_em_atendimento(session, telegram_id=8041)

    await message_handlers.on_message(
        FakeMessage(text="e o saque?", from_user=FakeUser(id=8041)), session
    )

    assert "openrouter" in capturado["url"]
    assert capturado["model"] == "google/gemma-4-31b-it:free"
    assert capturado["messages"][0]["role"] == "system"
    assert capturado["messages"][-1] == {"role": "user", "content": "e o saque?"}


async def test_chave_vai_em_header_e_nunca_na_url(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """URL com segredo vaza em log de proxy e em historico do navegador."""
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["header"] = request.headers.get("x-goog-api-key")
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        )

    provedor(handler)
    user, lead = await _lead_em_atendimento(session, telegram_id=8042)
    await message_handlers.on_message(
        FakeMessage(text="oi", from_user=FakeUser(id=8042)), session
    )

    assert capturado["header"] == "chave-de-teste-do-provedor"
    assert "chave-de-teste-do-provedor" not in capturado["url"]
    assert "key=" not in capturado["url"]


def test_chave_guardada_e_reversivel_e_mascarada():
    """Cifrada, nao hasheada: o bot precisa da chave em claro para chamar o
    provedor. O que a tela ve e a mascara."""
    from app.core.security import decrypt_secret

    chave = "AIzaSyExemploDeChaveFalsaParaTeste123"
    cifrada = encrypt_secret(chave)

    assert cifrada != chave, "nao guarda em claro"
    assert chave not in cifrada
    assert decrypt_secret(cifrada) == chave, "volta ao claro para uso"

    mascara = mask_secret(chave)
    assert mascara.startswith("AIza") and mascara.endswith("e123")
    assert chave not in mascara


async def test_base_traz_campanha_menu_e_apresentacao(
    session: AsyncSession, ia_ligada, provedor, campaign, global_content
):
    """A IA precisa saber de que campanha se trata e o que a conversa oferece.

    Antes a base era so a lista de respostas soltas: o modelo nao sabia o nome
    da campanha, nao tinha a apresentacao do produto e nao conhecia o menu —
    entao nao conseguia dizer "posso te explicar o cash out".
    """
    from app.core.config import settings as cfg
    from app.models import QualificationOption

    session.add(
        QualificationOption(
            tenant_id=cfg.tenant_id,
            campaign_id=campaign.id,
            key="cash_out",
            label="O que e a retirada",
            target=OptionTarget.INFORMATION,
            response_body="Retirar encerra sua participacao na rodada.",
        )
    )
    session.add(
        QualificationOption(
            tenant_id=cfg.tenant_id,
            campaign_id=campaign.id,
            key="humano",
            label="Falar com atendente",
            target=OptionTarget.HUMAN_SUPPORT,
        )
    )
    await session.flush()

    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        capturado.update(json.loads(request.content))
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        )

    provedor(handler)
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=8050, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    lead.last_touch_campaign_id = campaign.id
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)
    await funnel_service.transition(session, user, FunnelState.AI_SUPPORT, lead=lead)
    await session.flush()

    await message_handlers.on_message(
        FakeMessage(text="me explica o jogo", from_user=FakeUser(id=8050)), session
    )

    base = capturado["systemInstruction"]["parts"][0]["text"]
    assert campaign.name in base, "sabe de que campanha o lead veio"
    assert "Bem-vindo" in base or "Ola" in base, "tem a apresentacao do produto"
    assert "O que e a retirada" in base, "conhece o menu"
    assert "Retirar encerra sua participacao" in base, "tem a resposta cadastrada"
    assert "atendimento humano" in base.lower(), "sabe qual opcao leva a uma pessoa"


async def test_raciocinio_desligado_no_flash(
    session: AsyncSession, provedor, global_content
):
    """Teto de saida cobre raciocinio + texto: sem isso a resposta vem vazia."""
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        capturado.update(json.loads(request.content))
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        )

    provedor(handler)
    await _integracao(session, AiProvider.GEMINI, "gemini-2.5-flash")
    user, lead = await _lead_em_atendimento(session, telegram_id=8051)
    await message_handlers.on_message(
        FakeMessage(text="oi", from_user=FakeUser(id=8051)), session
    )

    assert capturado["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


async def test_modelo_pro_nao_recebe_orcamento_zero(
    session: AsyncSession, provedor, global_content
):
    """No `pro` o minimo e 128: mandar zero seria 400 e derrubaria a resposta."""
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        capturado.update(json.loads(request.content))
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        )

    provedor(handler)
    await _integracao(session, AiProvider.GEMINI, "gemini-2.5-pro")
    user, lead = await _lead_em_atendimento(session, telegram_id=8052)
    await message_handlers.on_message(
        FakeMessage(text="oi", from_user=FakeUser(id=8052)), session
    )

    assert "thinkingConfig" not in capturado["generationConfig"]


async def test_resposta_sem_texto_explica_o_motivo(
    session: AsyncSession, ia_ligada, provedor, global_content
):
    """"resposta vazia" nao diz se foi filtro, teto ou raciocinio."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}],
                "usageMetadata": {"thoughtsTokenCount": 476, "candidatesTokenCount": 0},
            },
        )

    provedor(handler)
    user, lead = await _lead_em_atendimento(session, telegram_id=8053)
    await message_handlers.on_message(
        FakeMessage(text="oi", from_user=FakeUser(id=8053)), session
    )

    falha = [
        e
        for e in (await session.execute(select(Event))).scalars()
        if e.event_type == EventType.AI_FAILED
    ][-1]
    motivo = falha.event_metadata["reason"]
    assert "MAX_TOKENS" in motivo and "476" in motivo, motivo
