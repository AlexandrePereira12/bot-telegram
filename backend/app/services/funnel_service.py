"""Maquina de estados do funil (M7, M8, M12).

Toda regra de negocio do funil vive aqui, nunca no handler do aiogram — o bot
e apenas uma interface (planejamento/arquitetura.md).

Duas invariantes de compliance sao aplicadas neste modulo e testadas em
tests/test_funnel_rules.py:

1. Age gate e bloqueante e persistido. Ninguem entra em QUALIFICATION sem
   age_confirmed=True no banco, mesmo reenviando /start.
2. Consentimento precisa estar aceito e vigente antes de qualquer
   comunicacao de marketing.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    ALLOWED_TRANSITIONS,
    ConsentStatus,
    EventType,
    FunnelState,
    LeadStatus,
    OptionTarget,
)
from app.core.logging import get_logger
from app.models import ConsentRecord, Lead, TelegramUser
from app.services.event_service import record_event

if TYPE_CHECKING:
    from app.services.content_service import ResolvedOption

logger = get_logger(__name__)


class FunnelError(Exception):
    """Transicao ou acao rejeitada por regra do funil."""


@dataclass(frozen=True)
class TransitionResult:
    state: FunnelState
    changed: bool


def can_transition(current: FunnelState, target: FunnelState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


async def transition(
    session: AsyncSession,
    user: TelegramUser,
    target: FunnelState,
    *,
    lead: Lead | None = None,
    event: EventType | None = None,
    metadata: dict | None = None,
) -> TransitionResult:
    """Aplica uma transicao de estado, validando o grafo e os guards.

    O estado e sempre persistido em telegram_users.current_state; nunca fica
    apenas na memoria do processo do bot.
    """
    if user.is_blocked:
        raise FunnelError("usuario bloqueado")

    current = FunnelState(user.current_state)
    if current == target:
        return TransitionResult(state=current, changed=False)

    if not can_transition(current, target):
        raise FunnelError(f"transicao invalida: {current} -> {target}")

    # Guard de compliance: entrar em QUALIFICATION exige idade confirmada e
    # consentimento aceito, verificados no banco e nao no fluxo do handler.
    if target == FunnelState.QUALIFICATION:
        _assert_age_gate_passed(user)
        _assert_consent_accepted(user)

    user.current_state = target

    if lead is not None:
        lead.status = _lead_status_for(target, lead.status)
        lead.last_interaction_at = datetime.now(UTC)
        if target == FunnelState.CONVERTED and lead.converted_at is None:
            lead.converted_at = datetime.now(UTC)

    if event is not None:
        await record_event(
            session,
            event,
            telegram_user_id=user.id,
            lead_id=lead.id if lead else None,
            campaign_id=lead.last_touch_campaign_id if lead else None,
            metadata=metadata,
        )

    logger.info(
        "transicao de estado",
        extra={"event": "STATE_CHANGED", "user_id": user.id, "state": target.value},
    )
    return TransitionResult(state=target, changed=True)


def _lead_status_for(state: FunnelState, current: LeadStatus) -> LeadStatus:
    mapping = {
        FunnelState.QUALIFICATION: LeadStatus.QUALIFYING,
        FunnelState.INFORMATION: LeadStatus.QUALIFIED,
        FunnelState.HUMAN_SUPPORT: LeadStatus.IN_SUPPORT,
        FunnelState.CONVERTED: LeadStatus.CONVERTED,
        FunnelState.EXIT: LeadStatus.LOST,
    }
    return mapping.get(state, current)


# --------------------------------------------------------------------- guards
def _assert_age_gate_passed(user: TelegramUser) -> None:
    """Age gate bloqueante.

    Quem foi reprovado nao volta ao funil por reenviar /start: age_rejected
    fica gravado no usuario. Esta e a regra com exposicao legal do projeto
    (planejamento/regras.md, compliance jogos/apostas).
    """
    if user.age_rejected:
        raise FunnelError("usuario reprovado no age gate")
    if not user.age_confirmed:
        raise FunnelError("idade nao confirmada")


def _assert_consent_accepted(user: TelegramUser) -> None:
    if user.consent_status != ConsentStatus.ACCEPTED:
        raise FunnelError("consentimento nao aceito")


async def has_active_consent(
    session: AsyncSession, telegram_user_id: int, consent_type: str = "marketing"
) -> bool:
    """Consentimento vigente para o tipo pedido.

    Vale o registro mais recente: aceito, nao revogado e na versao corrente
    dos termos. Todo envio de marketing (follow-up, notificacao) consulta
    isto antes de sair.
    """
    stmt = (
        select(ConsentRecord)
        .where(
            ConsentRecord.telegram_user_id == telegram_user_id,
            ConsentRecord.tenant_id == settings.tenant_id,
            ConsentRecord.consent_type == consent_type,
        )
        .order_by(desc(ConsentRecord.created_at), desc(ConsentRecord.id))
        .limit(1)
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        return False
    return (
        record.accepted
        and record.revoked_at is None
        and record.version >= settings.consent_version
    )


# ------------------------------------------------------------------ operacoes
async def accept_consent(
    session: AsyncSession,
    user: TelegramUser,
    lead: Lead | None,
    *,
    consent_type: str = "marketing",
    ip_hash: str | None = None,
) -> None:
    """Aceite de consentimento: novo registro versionado, nunca update do antigo."""
    session.add(
        ConsentRecord(
            tenant_id=settings.tenant_id,
            telegram_user_id=user.id,
            consent_type=consent_type,
            version=settings.consent_version,
            accepted=True,
            source="telegram",
            ip_hash=ip_hash,
        )
    )
    user.consent_status = ConsentStatus.ACCEPTED
    await record_event(
        session,
        EventType.CONSENT_ACCEPTED,
        telegram_user_id=user.id,
        lead_id=lead.id if lead else None,
        metadata={"version": settings.consent_version, "consent_type": consent_type},
    )
    await transition(session, user, FunnelState.AGE_GATE, lead=lead)


async def reject_consent(
    session: AsyncSession, user: TelegramUser, lead: Lead | None
) -> None:
    user.consent_status = ConsentStatus.REJECTED
    await transition(
        session, user, FunnelState.EXIT, lead=lead, event=EventType.CONSENT_REJECTED
    )


async def revoke_consent(
    session: AsyncSession, user: TelegramUser, *, consent_type: str = "marketing"
) -> None:
    """Revogacao: marca todos os registros vigentes e bloqueia envio futuro."""
    stmt = select(ConsentRecord).where(
        ConsentRecord.telegram_user_id == user.id,
        ConsentRecord.tenant_id == settings.tenant_id,
        ConsentRecord.consent_type == consent_type,
        ConsentRecord.revoked_at.is_(None),
    )
    now = datetime.now(UTC)
    for record in (await session.execute(stmt)).scalars():
        record.revoked_at = now
    user.consent_status = ConsentStatus.REVOKED
    await record_event(
        session,
        EventType.CONSENT_REVOKED,
        telegram_user_id=user.id,
        metadata={"consent_type": consent_type},
    )


async def confirm_age(
    session: AsyncSession, user: TelegramUser, lead: Lead | None
) -> None:
    user.age_confirmed = True
    user.age_rejected = False
    await record_event(
        session,
        EventType.AGE_CONFIRMED,
        telegram_user_id=user.id,
        lead_id=lead.id if lead else None,
        metadata={"min_age": settings.min_age},
    )
    await transition(
        session, user, FunnelState.QUALIFICATION, lead=lead, event=EventType.QUALIFICATION_STARTED
    )


async def reject_age(session: AsyncSession, user: TelegramUser, lead: Lead | None) -> None:
    """Reprovacao no age gate: terminal e persistida."""
    user.age_confirmed = False
    user.age_rejected = True
    await transition(
        session,
        user,
        FunnelState.EXIT,
        lead=lead,
        event=EventType.AGE_REJECTED,
        metadata={"min_age": settings.min_age},
    )


async def restart_from_exit(
    session: AsyncSession, user: TelegramUser, lead: Lead | None
) -> FunnelState:
    """Retomada de quem saiu por desistencia.

    Unico ponto autorizado a sair de EXIT — que e terminal no grafo. Retoma
    do ponto ja alcancado em vez de reiniciar do zero: quem ja aceitou os
    termos e confirmou idade nao responde tudo de novo (o que geraria um
    segundo consent_record identico e um par extra de eventos de
    consentimento).

    Reprovado no age gate nunca chega aqui: e barrado antes, no handler, e
    tambem pelo guard de QUALIFICATION.
    """
    if user.age_rejected:
        raise FunnelError("usuario reprovado no age gate")

    consent_ok = user.consent_status == ConsentStatus.ACCEPTED
    if consent_ok and user.age_confirmed:
        target = FunnelState.QUALIFICATION
    elif consent_ok:
        target = FunnelState.AGE_GATE
    else:
        target = FunnelState.WELCOME

    user.current_state = target
    if lead is not None:
        lead.status = _lead_status_for(target, lead.status)
        lead.last_interaction_at = datetime.now(UTC)

    logger.info(
        "funil retomado apos EXIT",
        extra={"event": "FUNNEL_RESUMED", "user_id": user.id, "state": target.value},
    )
    return target


async def reopen(
    session: AsyncSession, user: TelegramUser, lead: Lead | None
) -> FunnelState:
    """Reabre o funil depois de um atendimento encerrado.

    Reabrir nao e uma transicao: e um ciclo novo. Por isso acontece aqui, por
    atribuicao direta, em vez de afrouxar ALLOWED_TRANSITIONS — CONVERTED e
    EXIT continuam terminais no grafo.

    Consentimento e idade ja respondidos sao preservados: o lead volta direto
    a QUALIFICATION, sem reaceitar termos nem gerar novo consent_record.

    O historico do ciclo anterior fica intacto — `lead.converted_at` e as
    conversoes ja registradas nao sao apagados. Quem converteu e voltou
    continua sendo um lead convertido; o ciclo novo pode gerar outra conversao
    ou nenhuma.
    """
    if user.is_blocked:
        raise FunnelError("usuario bloqueado")
    # O age gate sobrevive a reabertura: quem foi reprovado nao reentra.
    _assert_age_gate_passed(user)
    _assert_consent_accepted(user)

    user.current_state = FunnelState.QUALIFICATION
    if lead is not None:
        lead.status = LeadStatus.QUALIFYING
        lead.last_interaction_at = datetime.now(UTC)

    await record_event(
        session,
        EventType.FUNNEL_REOPENED,
        telegram_user_id=user.id,
        lead_id=lead.id if lead else None,
        metadata={"previous_conversion_at": lead.converted_at.isoformat()}
        if lead and lead.converted_at
        else None,
    )
    logger.info(
        "funil reaberto apos encerramento",
        extra={"event": "FUNNEL_REOPENED", "user_id": user.id},
    )
    return FunnelState.QUALIFICATION


async def select_interest(
    session: AsyncSession, user: TelegramUser, lead: Lead | None, option: "ResolvedOption"
) -> OptionTarget:
    """Fim da qualificacao.

    O destino vem da propria opcao (coluna `target`), configurada no painel —
    assim uma opcao nova criada pelo operador sabe para onde levar o lead sem
    depender de nome reservado no codigo.
    """
    interest = option.key
    if lead is not None:
        lead.interest = interest

    # QUALIFICATION_COMPLETED marca a CONCLUSAO da etapa, entao so vale saindo
    # de QUALIFICATION. Trocar de interesse depois (ja em INFORMATION) emite
    # apenas INTEREST_SELECTED — senao o mesmo usuario apareceria concluindo a
    # qualificacao varias vezes e poluiria a analise de etapas.
    if FunnelState(user.current_state) == FunnelState.QUALIFICATION:
        await record_event(
            session,
            EventType.QUALIFICATION_COMPLETED,
            telegram_user_id=user.id,
            lead_id=lead.id if lead else None,
            metadata={"answer": interest},
        )
    await record_event(
        session,
        EventType.INTEREST_SELECTED,
        telegram_user_id=user.id,
        lead_id=lead.id if lead else None,
        metadata={"interest": interest},
    )

    if option.target == OptionTarget.HUMAN_SUPPORT:
        state, event = FunnelState.HUMAN_SUPPORT, EventType.HUMAN_SUPPORT_REQUESTED
    else:
        state, event = FunnelState.INFORMATION, EventType.FAQ_OPENED

    await transition(session, user, state, lead=lead, event=event)
    return option.target
