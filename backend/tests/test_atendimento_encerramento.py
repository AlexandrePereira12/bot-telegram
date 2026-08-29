"""Encerramento de atendimento com desfecho e reabertura do funil."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ConversationOutcome,
    ConversationStatus,
    EventType,
    FunnelState,
    LeadStatus,
    OperatorRole,
)
from app.models import ConsentRecord, Conversation, Conversion, Event
from app.services import conversation_service, funnel_service, lead_service
from app.services.auth_service import create_operator
from app.services.tracking_service import ORGANIC


async def _cenario(session: AsyncSession, telegram_id: int = 5001):
    """Lead que percorreu o funil e esta em atendimento humano."""
    operator = await create_operator(
        session,
        email=f"op{telegram_id}@teste.com",
        password="senha-de-teste-1234",
        role=OperatorRole.OPERATOR,
    )
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=telegram_id, first_name="Lead"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)

    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)
    await funnel_service.transition(session, user, FunnelState.HUMAN_SUPPORT, lead=lead)

    conversation = await conversation_service.get_or_create_conversation(session, user.id)
    await conversation_service.assign(session, conversation.id, operator)
    await session.flush()
    return operator, user, lead, conversation


async def _count(session: AsyncSession, model) -> int:
    return await session.scalar(select(func.count(model.id)))


# ------------------------------------------------------------------ desfecho
async def test_encerrar_sem_conversao_marca_lead_perdido(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)

    await conversation_service.close_with_outcome(
        session,
        conversation.id,
        operator,
        outcome=ConversationOutcome.NOT_CONVERTED,
        reason="fora do perfil",
    )
    await session.flush()

    assert user.current_state == FunnelState.EXIT, "ciclo encerrado"
    assert conversation.status == ConversationStatus.CLOSED
    assert conversation.outcome == ConversationOutcome.NOT_CONVERTED
    assert conversation.outcome_reason == "fora do perfil"
    assert conversation.closed_by_operator_id == operator.id
    assert conversation.ended_at is not None
    assert lead.status == LeadStatus.LOST
    assert lead.converted_at is None
    assert await _count(session, Conversion) == 0


async def test_encerrar_com_conversao_registra_uma_conversao(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)

    await conversation_service.close_with_outcome(
        session,
        conversation.id,
        operator,
        outcome=ConversationOutcome.CONVERTED,
        value=250.0,
        currency="BRL",
    )
    await session.flush()

    assert conversation.outcome == ConversationOutcome.CONVERTED
    assert lead.status == LeadStatus.CONVERTED
    assert lead.converted_at is not None
    assert await _count(session, Conversion) == 1

    conversao = (await session.execute(select(Conversion))).scalar_one()
    assert float(conversao.value) == 250.0
    assert conversao.external_id == f"manual:{conversation.id}"

    eventos = [
        e.event_type
        for e in (await session.execute(select(Event))).scalars()
    ]
    assert EventType.CONVERSION in eventos
    assert EventType.HUMAN_SUPPORT_CLOSED in eventos


async def test_encerrar_duas_vezes_e_recusado(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.CONVERTED
    )
    await session.flush()

    with pytest.raises(conversation_service.ConversationError, match="ja encerrado"):
        await conversation_service.close_with_outcome(
            session, conversation.id, operator, outcome=ConversationOutcome.CONVERTED
        )
    assert await _count(session, Conversion) == 1


async def test_conversao_e_deduplicada_por_conversa(session: AsyncSession):
    """Mesmo forcando o registro de novo, o external_id impede duplicar."""
    from app.services.conversion_service import register_conversion

    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.CONVERTED, value=100.0
    )
    await session.flush()

    _, criada = await register_conversion(
        session, lead_id=lead.id, external_id=f"manual:{conversation.id}", value=100.0
    )
    assert criada is False
    assert await _count(session, Conversion) == 1


# ----------------------------------------------------------------- reabertura
async def test_lead_volta_apos_encerramento_e_recomeca(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.CONVERTED, value=90.0
    )
    await session.flush()
    convertido_em = lead.converted_at

    # Encerrar levou o funil ao estado terminal — e o que sinaliza ciclo
    # fechado quando o lead volta.
    assert user.current_state == FunnelState.CONVERTED

    await funnel_service.reopen(session, user, lead)
    await session.flush()

    assert user.current_state == FunnelState.QUALIFICATION
    assert lead.status == LeadStatus.QUALIFYING
    assert lead.converted_at == convertido_em, "historico do ciclo anterior intacto"
    assert await _count(session, Conversion) == 1, "reabrir nao apaga a conversao"


async def test_reabertura_cria_conversa_nova(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.NOT_CONVERTED
    )
    await session.flush()

    nova = await conversation_service.get_or_create_conversation(session, user.id)
    await session.flush()

    assert nova.id != conversation.id, "ciclo novo tem sua propria conversa"
    assert nova.status == ConversationStatus.OPEN
    assert nova.outcome is None
    assert await _count(session, Conversation) == 2


async def test_reabertura_nao_repete_consentimento(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)
    consentimentos = await _count(session, ConsentRecord)
    aceites = await session.scalar(
        select(func.count(Event.id)).where(
            Event.event_type == EventType.CONSENT_ACCEPTED
        )
    )

    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.NOT_CONVERTED
    )
    await funnel_service.reopen(session, user, lead)
    await session.flush()

    assert await _count(session, ConsentRecord) == consentimentos
    assert (
        await session.scalar(
            select(func.count(Event.id)).where(
                Event.event_type == EventType.CONSENT_ACCEPTED
            )
        )
        == aceites
    )


async def test_reabertura_nao_burla_o_age_gate(session: AsyncSession):
    """Quem foi reprovado na idade continua bloqueado mesmo apos encerramento."""
    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.NOT_CONVERTED
    )
    user.age_confirmed = False
    user.age_rejected = True
    await session.flush()

    with pytest.raises(funnel_service.FunnelError, match="reprovado no age gate"):
        await funnel_service.reopen(session, user, lead)


async def test_reabertura_exige_consentimento_vigente(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.NOT_CONVERTED
    )
    await funnel_service.revoke_consent(session, user)
    await session.flush()

    with pytest.raises(funnel_service.FunnelError, match="consentimento"):
        await funnel_service.reopen(session, user, lead)


async def test_reabertura_recusa_usuario_bloqueado(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)
    await conversation_service.close_with_outcome(
        session, conversation.id, operator, outcome=ConversationOutcome.NOT_CONVERTED
    )
    user.is_blocked = True
    await session.flush()

    with pytest.raises(funnel_service.FunnelError, match="bloqueado"):
        await funnel_service.reopen(session, user, lead)


# ---------------------------------------------------------------- devolucao
async def test_devolver_sem_encerrar_nao_pede_desfecho(session: AsyncSession):
    operator, user, lead, conversation = await _cenario(session)

    await conversation_service.release(session, conversation.id, operator)
    await session.flush()

    assert conversation.status == ConversationStatus.OPEN
    assert conversation.assigned_to is None
    assert conversation.outcome is None, "devolver nao e encerrar"
    assert conversation.ended_at is None


# ------------------------------------------------------- mensagem com anexo
async def test_mensagem_do_operador_guarda_o_anexo(session: AsyncSession):
    from app.core.enums import MediaType, MessageDirection, SenderType
    from app.models import Message

    operator, user, lead, conversation = await _cenario(session, telegram_id=5099)

    await conversation_service.record_message(
        session,
        conversation,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.OPERATOR,
        sender_id=operator.id,
        content="segue a tabela",
        message_type="photo",
        media_path="tenant/abc.png",
        media_type=MediaType.PHOTO,
    )
    await session.flush()

    msg = (
        await session.execute(
            select(Message).where(Message.media_path.is_not(None))
        )
    ).scalar_one()
    assert msg.media_type == MediaType.PHOTO
    assert msg.media_path == "tenant/abc.png"
    assert msg.sender_type == SenderType.OPERATOR


def test_resposta_do_operador_exige_texto_ou_anexo():
    """Enviar vazio nao faz sentido; com anexo, a legenda e opcional."""
    import pytest as _pytest
    from pydantic import ValidationError

    from app.core.enums import MediaType
    from app.schemas import OperatorReply

    with _pytest.raises(ValidationError):
        OperatorReply(content="   ")

    so_anexo = OperatorReply(content="", media_path="t/x.png", media_type=MediaType.PHOTO)
    assert so_anexo.media_path == "t/x.png"
    assert OperatorReply(content="texto").content == "texto"
