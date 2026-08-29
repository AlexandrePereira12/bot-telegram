"""Regras do funil e compliance.

Cada teste aqui corresponde a uma afirmacao de planejamento/regras.md.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ALLOWED_TRANSITIONS, ConsentStatus, FunnelState
from app.services import funnel_service, lead_service
from app.services.tracking_service import ORGANIC


async def _new_user(session: AsyncSession, telegram_id: int = 1001):
    user, _ = await lead_service.get_or_create_user(
        session, telegram_id=telegram_id, first_name="Teste"
    )
    lead, _ = await lead_service.get_or_create_lead(session, user, ORGANIC)
    return user, lead


async def _advance_to_age_gate(session: AsyncSession, user, lead) -> None:
    await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
    await funnel_service.transition(session, user, FunnelState.CONSENT, lead=lead)
    await funnel_service.accept_consent(session, user, lead)


# ------------------------------------------------------------------- age gate
async def test_age_gate_bloqueia_qualificacao_sem_confirmacao(session: AsyncSession):
    user, lead = await _new_user(session)
    await _advance_to_age_gate(session, user, lead)
    assert user.current_state == FunnelState.AGE_GATE

    with pytest.raises(funnel_service.FunnelError, match="idade nao confirmada"):
        await funnel_service.transition(session, user, FunnelState.QUALIFICATION, lead=lead)


async def test_age_rejeitado_nao_reentra_no_funil(session: AsyncSession):
    """Reprovado no age gate nao volta a QUALIFICATION nem reenviando /start."""
    user, lead = await _new_user(session)
    await _advance_to_age_gate(session, user, lead)
    await funnel_service.reject_age(session, user, lead)

    assert user.current_state == FunnelState.EXIT
    assert user.age_rejected is True

    # Mesmo forcando o estado de volta, o guard persistido bloqueia.
    user.current_state = FunnelState.AGE_GATE
    with pytest.raises(funnel_service.FunnelError, match="reprovado no age gate"):
        await funnel_service.transition(session, user, FunnelState.QUALIFICATION, lead=lead)


async def test_exit_e_terminal_e_nao_leva_a_converted(session: AsyncSession):
    """FSM corrigida: o documento original ligava EXIT a CONVERTED."""
    assert ALLOWED_TRANSITIONS[FunnelState.EXIT] == set()
    assert FunnelState.CONVERTED not in ALLOWED_TRANSITIONS[FunnelState.EXIT]

    user, lead = await _new_user(session)
    user.current_state = FunnelState.EXIT
    with pytest.raises(funnel_service.FunnelError, match="transicao invalida"):
        await funnel_service.transition(session, user, FunnelState.CONVERTED, lead=lead)


async def test_converted_alcancavel_a_partir_da_qualificacao(session: AsyncSession):
    user, lead = await _new_user(session)
    await _advance_to_age_gate(session, user, lead)
    await funnel_service.confirm_age(session, user, lead)
    assert user.current_state == FunnelState.QUALIFICATION

    await funnel_service.transition(session, user, FunnelState.CONVERTED, lead=lead)
    assert user.current_state == FunnelState.CONVERTED
    assert lead.converted_at is not None


# --------------------------------------------------------------- consentimento
async def test_qualificacao_exige_consentimento_aceito(session: AsyncSession):
    user, lead = await _new_user(session)
    user.current_state = FunnelState.AGE_GATE
    user.age_confirmed = True
    user.consent_status = ConsentStatus.PENDING

    with pytest.raises(funnel_service.FunnelError, match="consentimento nao aceito"):
        await funnel_service.transition(session, user, FunnelState.QUALIFICATION, lead=lead)


async def test_consentimento_revogado_invalida_envio(session: AsyncSession):
    user, lead = await _new_user(session)
    await _advance_to_age_gate(session, user, lead)
    await session.flush()
    assert await funnel_service.has_active_consent(session, user.id) is True

    await funnel_service.revoke_consent(session, user)
    await session.flush()
    assert await funnel_service.has_active_consent(session, user.id) is False
    assert user.consent_status == ConsentStatus.REVOKED


async def test_consentimento_e_versionado_nao_editado(session: AsyncSession):
    from sqlalchemy import func, select

    from app.models import ConsentRecord

    user, lead = await _new_user(session)
    await _advance_to_age_gate(session, user, lead)
    await funnel_service.revoke_consent(session, user)
    user.current_state = FunnelState.CONSENT
    user.consent_status = ConsentStatus.PENDING
    await funnel_service.accept_consent(session, user, lead)
    await session.flush()

    total = await session.scalar(
        select(func.count(ConsentRecord.id)).where(ConsentRecord.telegram_user_id == user.id)
    )
    # Reaceite gera registro novo em vez de reescrever o revogado.
    assert total == 2


async def test_usuario_bloqueado_nao_transita(session: AsyncSession):
    user, lead = await _new_user(session)
    user.is_blocked = True
    with pytest.raises(funnel_service.FunnelError, match="bloqueado"):
        await funnel_service.transition(session, user, FunnelState.WELCOME, lead=lead)
