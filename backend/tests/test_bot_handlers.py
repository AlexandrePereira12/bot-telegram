"""Handlers do bot exercitados de ponta a ponta (M6, M7, M8).

Os demais testes chamam os services diretamente. Aqui os proprios handlers do
aiogram rodam, com dublês no lugar da API do Telegram — é o caminho que o
usuario real percorre.
"""

from dataclasses import dataclass, field
from io import BytesIO

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import commands
from app.bot.handlers import funnel as funnel_handlers
from app.core.enums import ConsentStatus, EventType, FunnelState, SenderType
from app.models import Campaign, ConsentRecord, Event, MediaObject, TelegramUser
from app.models import Message as MessageRow
from app.services import lead_service, tracking_service


# --------------------------------------------------------------------- dublês
@dataclass
class FakeUser:
    id: int = 7001
    username: str | None = "tester"
    first_name: str | None = "Teste"
    language_code: str | None = "pt-br"


@dataclass
class FakeSent:
    message_id: int = 1


@dataclass
class FakeFile:
    """Anexo do Telegram: o handler so precisa do tamanho e do file_id."""

    file_id: str = "file-1"
    file_size: int = 1024


@dataclass
class FakeBot:
    """Dublê do bot para o download do anexo recebido."""

    conteudo: bytes = b""
    baixados: list[str] = field(default_factory=list)

    async def download(self, alvo: FakeFile) -> BytesIO:
        self.baixados.append(alvo.file_id)
        return BytesIO(self.conteudo)


@dataclass
class FakeMessage:
    from_user: FakeUser = field(default_factory=FakeUser)
    message_id: int = 1
    text: str | None = "/start"
    caption: str | None = None
    content_type: str = "text"
    answers: list[str] = field(default_factory=list)
    # Anexos: a mensagem real do aiogram sempre expõe os campos, nulos quando
    # nao ha midia. O handler decide por eles.
    photo: list[FakeFile] | None = None
    video: FakeFile | None = None
    voice: FakeFile | None = None
    audio: FakeFile | None = None
    document: FakeFile | None = None
    bot: FakeBot | None = None

    async def answer(self, text: str, reply_markup=None) -> FakeSent:
        self.answers.append(text)
        return FakeSent(message_id=len(self.answers))


@dataclass
class FakeCommand:
    args: str | None = None


@dataclass
class FakeCallback:
    data: str
    from_user: FakeUser = field(default_factory=FakeUser)
    message: FakeMessage = field(default_factory=FakeMessage)
    answered: bool = False

    async def answer(self) -> None:
        self.answered = True


async def _state(session: AsyncSession, telegram_id: int = 7001) -> FunnelState:
    user = (
        await session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
    ).scalar_one()
    return FunnelState(user.current_state)


async def _count_events(session: AsyncSession, event_type: EventType) -> int:
    return await session.scalar(
        select(func.count(Event.id)).where(Event.event_type == event_type)
    )


async def _run_full_funnel(session: AsyncSession, message: FakeMessage) -> None:
    await commands.cmd_start(message, FakeCommand(), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_confirm(FakeCallback("age:confirm"), session)


# ------------------------------------------------------------------ caminho feliz
async def test_start_cria_usuario_lead_e_evento(session: AsyncSession, campaign):
    token = await tracking_service.create_token(session, campaign_id=campaign.id, source="meta")
    message = FakeMessage()

    await commands.cmd_start(message, FakeCommand(args=token.token), session)

    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    lead = await lead_service.get_lead_by_user(session, user.id)

    assert lead is not None
    assert lead.last_touch_campaign_id == campaign.id, "atribuicao gravada a partir do token"
    assert await _count_events(session, EventType.USER_STARTED) == 1
    assert user.current_state == FunnelState.CONSENT, "para no consentimento"
    assert len(message.answers) == 2, "welcome + termos"


async def test_start_com_token_invalido_nao_quebra_o_funil(session: AsyncSession):
    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(args="t_naoexiste"), session)

    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    lead = await lead_service.get_lead_by_user(session, user.id)
    assert lead.source == "organic"
    assert user.current_state == FunnelState.CONSENT


async def test_funil_completo_ate_atendimento(session: AsyncSession):
    message = FakeMessage()
    await _run_full_funnel(session, message)
    assert await _state(session) == FunnelState.QUALIFICATION

    await funnel_handlers.on_interest(FakeCallback("interest:human_support"), session)
    assert await _state(session) == FunnelState.HUMAN_SUPPORT
    assert await _count_events(session, EventType.HUMAN_SUPPORT_REQUESTED) == 1


async def test_toda_saida_do_bot_vira_mensagem_registrada(session: AsyncSession):
    """Nenhuma resposta do bot sai sem virar linha em `messages`."""
    message = FakeMessage()
    consent = FakeCallback("consent:accept")
    age = FakeCallback("age:confirm")

    await commands.cmd_start(message, FakeCommand(), session)
    await funnel_handlers.on_consent_accept(consent, session)
    await funnel_handlers.on_age_confirm(age, session)

    enviadas = message.answers + consent.message.answers + age.message.answers
    rows = list(
        (
            await session.execute(
                select(MessageRow).where(MessageRow.sender_type == SenderType.BOT)
            )
        ).scalars()
    )
    assert len(enviadas) == 4, "welcome, termos, age gate, qualificacao"
    assert [r.content for r in rows] == enviadas


# --------------------------------------------------------------------- age gate
async def test_age_rejeitado_bloqueia_novo_start(session: AsyncSession):
    """Reprovado no age gate nao volta ao funil reenviando /start."""
    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_reject(FakeCallback("age:reject"), session)

    assert await _state(session) == FunnelState.EXIT

    retry = FakeMessage()
    await commands.cmd_start(retry, FakeCommand(), session)

    assert await _state(session) == FunnelState.EXIT, "permanece fora do funil"
    assert "restrito a maiores" in retry.answers[-1]


async def test_age_confirm_apos_rejeicao_nao_reabre_o_funil(session: AsyncSession):
    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_reject(FakeCallback("age:reject"), session)

    # Reclicar o botao antigo de confirmacao nao deve reabrir nada.
    await funnel_handlers.on_age_confirm(FakeCallback("age:confirm"), session)
    assert await _state(session) == FunnelState.EXIT


# ------------------------------------------------------------------- re-entrada
async def test_retomada_apos_desistencia_nao_repete_consentimento(session: AsyncSession):
    """Quem saiu depois de qualificar retoma sem responder tudo de novo."""
    message = FakeMessage()
    await _run_full_funnel(session, message)

    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    lead = await lead_service.get_lead_by_user(session, user.id)

    from app.services import funnel_service

    await funnel_service.transition(session, user, FunnelState.EXIT, lead=lead)
    assert await _state(session) == FunnelState.EXIT

    consent_antes = await session.scalar(select(func.count(ConsentRecord.id)))
    eventos_antes = await _count_events(session, EventType.CONSENT_ACCEPTED)

    retry = FakeMessage()
    await commands.cmd_start(retry, FakeCommand(), session)

    assert await _state(session) == FunnelState.QUALIFICATION, "retoma na qualificacao"
    assert await session.scalar(select(func.count(ConsentRecord.id))) == consent_antes, (
        "nao duplica registro de consentimento"
    )
    assert await _count_events(session, EventType.CONSENT_ACCEPTED) == eventos_antes


async def test_retomada_com_consentimento_pendente_volta_ao_age_gate(session: AsyncSession):
    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    assert await _state(session) == FunnelState.AGE_GATE

    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    lead = await lead_service.get_lead_by_user(session, user.id)

    from app.services import funnel_service

    await funnel_service.transition(session, user, FunnelState.EXIT, lead=lead)

    retry = FakeMessage()
    await commands.cmd_start(retry, FakeCommand(), session)
    assert await _state(session) == FunnelState.AGE_GATE
    assert str(18) in retry.answers[-1]


async def test_callback_repetido_nao_reprocessa(session: AsyncSession):
    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)

    assert await _count_events(session, EventType.CONSENT_ACCEPTED) == 1
    assert await session.scalar(select(func.count(ConsentRecord.id))) == 1


# --------------------------------------------------------------------- revogacao
async def test_comando_parar_revoga_consentimento(session: AsyncSession):
    from app.services import funnel_service

    message = FakeMessage()
    await _run_full_funnel(session, message)

    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    assert await funnel_service.has_active_consent(session, user.id) is True

    await commands.cmd_stop(FakeMessage(text="/parar"), session)
    await session.flush()

    assert await funnel_service.has_active_consent(session, user.id) is False
    assert user.consent_status == ConsentStatus.REVOKED


async def test_usuario_bloqueado_nao_avanca(session: AsyncSession):
    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(), session)

    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    user.is_blocked = True
    await session.flush()

    retry = FakeMessage()
    await commands.cmd_start(retry, FakeCommand(), session)
    assert retry.answers == ["Este atendimento esta encerrado."]


async def test_interesse_desconhecido_e_ignorado(session: AsyncSession):
    message = FakeMessage()
    await _run_full_funnel(session, message)

    await funnel_handlers.on_interest(FakeCallback("interest:injetado"), session)
    assert await _state(session) == FunnelState.QUALIFICATION


@pytest.mark.parametrize("interest,expected", [
    ("service_info", FunnelState.INFORMATION),
    ("faq", FunnelState.INFORMATION),
    ("human_support", FunnelState.HUMAN_SUPPORT),
])
async def test_roteamento_por_interesse(
    session: AsyncSession, interest: str, expected: FunnelState
):
    message = FakeMessage()
    await _run_full_funnel(session, message)
    await funnel_handlers.on_interest(FakeCallback(f"interest:{interest}"), session)
    assert await _state(session) == expected


async def test_trocar_de_interesse_nao_repete_qualificacao_concluida(session: AsyncSession):
    """QUALIFICATION_COMPLETED marca a conclusao da etapa, uma vez so."""
    message = FakeMessage()
    await _run_full_funnel(session, message)

    await funnel_handlers.on_interest(FakeCallback("interest:service_info"), session)
    await funnel_handlers.on_interest(FakeCallback("interest:faq"), session)
    await funnel_handlers.on_interest(FakeCallback("interest:human_support"), session)

    assert await _count_events(session, EventType.QUALIFICATION_COMPLETED) == 1
    # Cada escolha continua registrada individualmente.
    assert await _count_events(session, EventType.INTEREST_SELECTED) == 3


# ---------------------------------------------- conteudo por campanha (M-content)
async def test_bot_usa_o_texto_da_campanha_do_lead(
    session: AsyncSession, campaign, global_content
):
    """Lead que entra pelo token da campanha recebe o texto DELA."""
    from app.core.config import settings
    from app.core.enums import FunnelStep
    from app.models import FunnelContent

    session.add(
        FunnelContent(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            step=FunnelStep.WELCOME,
            body="Chegou pelo anuncio de futebol!",
        )
    )
    token = await tracking_service.create_token(session, campaign_id=campaign.id)
    await session.flush()

    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(args=token.token), session)

    assert message.answers[0] == "Chegou pelo anuncio de futebol!"


async def test_lead_organico_recebe_o_texto_global(
    session: AsyncSession, campaign, global_content
):
    from app.core.config import settings
    from app.core.enums import FunnelStep
    from app.models import FunnelContent

    session.add(
        FunnelContent(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            step=FunnelStep.WELCOME,
            body="Texto exclusivo da campanha",
        )
    )
    await session.flush()

    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(), session)

    assert "Texto exclusivo" not in message.answers[0]
    assert "Bem-vindo" in message.answers[0]


async def test_opcao_criada_no_painel_roteia_pelo_target(
    session: AsyncSession, campaign, global_content
):
    """Opcao nova com target=HUMAN_SUPPORT leva o lead ao atendimento."""
    from app.core.config import settings
    from app.core.enums import OptionTarget
    from app.models import QualificationOption

    session.add(
        QualificationOption(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            key="quero_falar",
            label="Quero falar com alguem",
            target=OptionTarget.HUMAN_SUPPORT,
        )
    )
    token = await tracking_service.create_token(session, campaign_id=campaign.id)
    await session.flush()

    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(args=token.token), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_confirm(FakeCallback("age:confirm"), session)

    await funnel_handlers.on_interest(FakeCallback("interest:quero_falar"), session)
    assert await _state(session) == FunnelState.HUMAN_SUPPORT


async def test_opcao_de_outra_campanha_nao_e_aceita(
    session: AsyncSession, campaign, global_content
):
    """Callback com chave que nao pertence a campanha do lead e ignorado."""
    from app.core.config import settings
    from app.models import QualificationOption

    outra = Campaign(
        tenant_id=settings.tenant_id, name="Outra", source="x", external_id="cx"
    )
    session.add(outra)
    await session.flush()
    session.add(
        QualificationOption(
            tenant_id=settings.tenant_id,
            campaign_id=outra.id,
            key="exclusiva_da_outra",
            label="Exclusiva",
        )
    )
    token = await tracking_service.create_token(session, campaign_id=campaign.id)
    await session.flush()

    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(args=token.token), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_confirm(FakeCallback("age:confirm"), session)

    await funnel_handlers.on_interest(FakeCallback("interest:exclusiva_da_outra"), session)
    assert await _state(session) == FunnelState.QUALIFICATION, "estado nao muda"


# ------------------------------------------- reabertura pelo proprio Telegram
async def test_lead_que_volta_apos_encerramento_recomeca_pelo_bot(
    session: AsyncSession, global_content
):
    """O gatilho real: o lead manda mensagem depois do atendimento encerrado."""
    from app.core.enums import ConversationOutcome, OperatorRole
    from app.services import conversation_service
    from app.services.auth_service import create_operator

    message = FakeMessage()
    await _run_full_funnel(session, message)
    await funnel_handlers.on_interest(FakeCallback("interest:human_support"), session)
    assert await _state(session) == FunnelState.HUMAN_SUPPORT

    operator = await create_operator(
        session, email="op@teste.com", password="senha-de-teste-1234", role=OperatorRole.OPERATOR
    )
    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    conversa = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.close_with_outcome(
        session, conversa.id, operator, outcome=ConversationOutcome.CONVERTED, value=50.0
    )
    await session.flush()

    # Lead volta e escreve qualquer coisa.
    from app.bot.handlers import messages as message_handlers

    de_volta = FakeMessage(text="oi, preciso de novo")
    await message_handlers.on_message(de_volta, session)

    assert await _state(session) == FunnelState.QUALIFICATION, "recomecou o atendimento"
    assert "procura" in de_volta.answers[-1].lower()


async def test_start_apos_encerramento_tambem_recomeca(
    session: AsyncSession, global_content
):
    from app.core.enums import ConversationOutcome, OperatorRole
    from app.services import conversation_service
    from app.services.auth_service import create_operator

    message = FakeMessage()
    await _run_full_funnel(session, message)
    await funnel_handlers.on_interest(FakeCallback("interest:human_support"), session)

    operator = await create_operator(
        session, email="op2@teste.com", password="senha-de-teste-1234", role=OperatorRole.OPERATOR
    )
    user = (
        await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == 7001))
    ).scalar_one()
    conversa = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.close_with_outcome(
        session, conversa.id, operator, outcome=ConversationOutcome.NOT_CONVERTED
    )
    await session.flush()

    retry = FakeMessage()
    await commands.cmd_start(retry, FakeCommand(), session)
    assert await _state(session) == FunnelState.QUALIFICATION


async def test_atendimento_em_aberto_nao_reabre(session: AsyncSession, global_content):
    """Conversa ainda aberta segue em atendimento; nao vira ciclo novo."""
    from app.bot.handlers import messages as message_handlers

    message = FakeMessage()
    await _run_full_funnel(session, message)
    await funnel_handlers.on_interest(FakeCallback("interest:human_support"), session)

    nova = FakeMessage(text="alguem ai?")
    await message_handlers.on_message(nova, session)

    assert await _state(session) == FunnelState.HUMAN_SUPPORT


async def test_bot_responde_com_o_texto_da_opcao_escolhida(
    session: AsyncSession, campaign, global_content
):
    """Cada opcao entrega a resposta que o painel configurou para ela."""
    from app.core.config import settings
    from app.core.enums import OptionTarget
    from app.models import QualificationOption

    session.add_all(
        [
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="precos",
                label="Ver precos",
                target=OptionTarget.INFORMATION,
                response_body="Planos a partir de R$ 49 por mes.",
                sort_order=10,
            ),
            QualificationOption(
                tenant_id=settings.tenant_id,
                campaign_id=campaign.id,
                key="horario",
                label="Horario de atendimento",
                target=OptionTarget.INFORMATION,
                response_body="Atendemos de segunda a sexta, das 9h as 18h.",
                sort_order=20,
            ),
        ]
    )
    token = await tracking_service.create_token(session, campaign_id=campaign.id)
    await session.flush()

    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(args=token.token), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_confirm(FakeCallback("age:confirm"), session)

    escolha = FakeCallback("interest:precos")
    await funnel_handlers.on_interest(escolha, session)
    assert escolha.message.answers[-1] == "Planos a partir de R$ 49 por mes."

    outra = FakeCallback("interest:horario")
    await funnel_handlers.on_interest(outra, session)
    assert outra.message.answers[-1] == "Atendemos de segunda a sexta, das 9h as 18h."


async def test_opcao_sem_resposta_usa_a_mensagem_generica(
    session: AsyncSession, campaign, global_content
):
    from app.core.config import settings
    from app.models import QualificationOption

    session.add(
        QualificationOption(
            tenant_id=settings.tenant_id,
            campaign_id=campaign.id,
            key="generico",
            label="Sem resposta propria",
        )
    )
    token = await tracking_service.create_token(session, campaign_id=campaign.id)
    await session.flush()

    message = FakeMessage()
    await commands.cmd_start(message, FakeCommand(args=token.token), session)
    await funnel_handlers.on_consent_accept(FakeCallback("consent:accept"), session)
    await funnel_handlers.on_age_confirm(FakeCallback("age:confirm"), session)

    escolha = FakeCallback("interest:generico")
    await funnel_handlers.on_interest(escolha, session)
    # Texto da etapa INFORMATION, com {interest} preenchido pelo rotulo.
    assert "Sem resposta propria" in escolha.message.answers[-1]


# ------------------------------------------------------------------- anexos
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def test_foto_sem_legenda_e_registrada_com_o_arquivo(
    session: AsyncSession, global_content
):
    """Foto sem texto nao casava com handler nenhum e desaparecia.

    Aqui a mensagem entra em `messages` com o anexo ja no volume — e o painel
    tem o que exibir, em vez de um buraco na conversa.
    """
    from app.bot.handlers import messages as message_handlers

    foto = FakeMessage(
        text=None,
        caption=None,
        content_type="photo",
        photo=[FakeFile(file_id="foto-pequena"), FakeFile(file_id="foto-grande")],
        bot=FakeBot(conteudo=JPEG),
    )
    await message_handlers.on_message(foto, session)

    row = (
        await session.execute(
            select(MessageRow).where(MessageRow.sender_type == SenderType.USER)
        )
    ).scalar_one()
    midia = await session.get(MediaObject, row.media_id) if row.media_id else None

    assert row.media_id, "anexo gravado no banco"
    assert midia is not None and midia.content == JPEG, "bytes vao para o banco"
    assert row.media_type == "photo"
    assert row.content is None
    assert foto.bot.baixados == ["foto-grande"], "maior resolucao disponivel"


async def test_anexo_grande_demais_nao_impede_o_registro(
    session: AsyncSession, global_content
):
    from app.bot.handlers import messages as message_handlers
    from app.core.config import settings

    acima = (settings.max_media_mb * 1024 * 1024) + 1
    foto = FakeMessage(
        text=None,
        caption="olha isso",
        content_type="photo",
        photo=[FakeFile(file_id="gigante", file_size=acima)],
        bot=FakeBot(conteudo=JPEG),
    )
    await message_handlers.on_message(foto, session)

    row = (
        await session.execute(
            select(MessageRow).where(MessageRow.sender_type == SenderType.USER)
        )
    ).scalar_one()

    assert row.media_id is None
    assert row.content == "olha isso", "a conversa continua registrada sem o anexo"
    assert foto.bot.baixados == [], "nao chega a baixar"
