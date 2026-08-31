"""Enumeracoes de dominio.

Espelham planejamento/arquitetura.md. A FSM aqui ja e a corrigida: EXIT e
terminal e NUNCA leva a CONVERTED.
"""

from enum import StrEnum


class FunnelState(StrEnum):
    NEW = "NEW"
    WELCOME = "WELCOME"
    CONSENT = "CONSENT"
    AGE_GATE = "AGE_GATE"
    QUALIFICATION = "QUALIFICATION"
    INFORMATION = "INFORMATION"
    #: Atendimento por IA. Existe separado de HUMAN_SUPPORT para a metrica
    #: distinguir o que a IA resolveu do que precisou de gente.
    AI_SUPPORT = "AI_SUPPORT"
    HUMAN_SUPPORT = "HUMAN_SUPPORT"
    CONVERTED = "CONVERTED"
    EXIT = "EXIT"


#: Transicoes permitidas. Fonte unica da verdade da maquina de estados.
#: EXIT e CONVERTED sao terminais.
ALLOWED_TRANSITIONS: dict[FunnelState, set[FunnelState]] = {
    FunnelState.NEW: {FunnelState.WELCOME},
    FunnelState.WELCOME: {FunnelState.CONSENT},
    FunnelState.CONSENT: {FunnelState.AGE_GATE, FunnelState.EXIT},
    FunnelState.AGE_GATE: {FunnelState.QUALIFICATION, FunnelState.EXIT},
    FunnelState.QUALIFICATION: {
        FunnelState.INFORMATION,
        FunnelState.AI_SUPPORT,
        FunnelState.HUMAN_SUPPORT,
        FunnelState.CONVERTED,
        FunnelState.EXIT,
    },
    FunnelState.INFORMATION: {
        FunnelState.AI_SUPPORT,
        FunnelState.HUMAN_SUPPORT,
        FunnelState.CONVERTED,
        FunnelState.EXIT,
    },
    #: A IA atende ate o lead insistir por gente — dai o caminho para
    #: HUMAN_SUPPORT. Voltar a INFORMATION mantem o menu utilizavel.
    FunnelState.AI_SUPPORT: {
        FunnelState.INFORMATION,
        FunnelState.HUMAN_SUPPORT,
        FunnelState.CONVERTED,
        FunnelState.EXIT,
    },
    FunnelState.HUMAN_SUPPORT: {
        FunnelState.INFORMATION,
        FunnelState.CONVERTED,
        FunnelState.EXIT,
    },
    FunnelState.CONVERTED: set(),
    FunnelState.EXIT: set(),
}

TERMINAL_STATES = {FunnelState.EXIT, FunnelState.CONVERTED}


class EventType(StrEnum):
    USER_STARTED = "USER_STARTED"
    WELCOME_SENT = "WELCOME_SENT"
    CONSENT_VIEWED = "CONSENT_VIEWED"
    CONSENT_ACCEPTED = "CONSENT_ACCEPTED"
    CONSENT_REJECTED = "CONSENT_REJECTED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    AGE_CONFIRMED = "AGE_CONFIRMED"
    AGE_REJECTED = "AGE_REJECTED"
    QUALIFICATION_STARTED = "QUALIFICATION_STARTED"
    QUALIFICATION_COMPLETED = "QUALIFICATION_COMPLETED"
    INTEREST_SELECTED = "INTEREST_SELECTED"
    FAQ_OPENED = "FAQ_OPENED"
    AI_SUPPORT_STARTED = "AI_SUPPORT_STARTED"
    AI_REPLIED = "AI_REPLIED"
    AI_FAILED = "AI_FAILED"
    #: Pedido de atendente feito DURANTE o atendimento por IA. Separado de
    #: HUMAN_SUPPORT_REQUESTED (que marca a entrada no atendimento) porque e
    #: so este que conta como insistencia — escolher "falar com atendente" no
    #: menu e como se chega aqui, nao um sinal de que a IA falhou.
    AI_HANDOFF_REQUESTED = "AI_HANDOFF_REQUESTED"
    HUMAN_SUPPORT_REQUESTED = "HUMAN_SUPPORT_REQUESTED"
    HUMAN_SUPPORT_ASSIGNED = "HUMAN_SUPPORT_ASSIGNED"
    HUMAN_SUPPORT_RELEASED = "HUMAN_SUPPORT_RELEASED"
    HUMAN_SUPPORT_CLOSED = "HUMAN_SUPPORT_CLOSED"
    HUMAN_SUPPORT_REOPENED = "HUMAN_SUPPORT_REOPENED"
    FUNNEL_REOPENED = "FUNNEL_REOPENED"
    MESSAGE_SENT = "MESSAGE_SENT"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    FOLLOWUP_SCHEDULED = "FOLLOWUP_SCHEDULED"
    FOLLOWUP_SENT = "FOLLOWUP_SENT"
    CONVERSION = "CONVERSION"
    USER_BLOCKED = "USER_BLOCKED"


class LeadStatus(StrEnum):
    NEW = "NEW"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    IN_SUPPORT = "IN_SUPPORT"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class OperatorRole(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    OPERATOR = "OPERATOR"
    ANALYST = "ANALYST"
    SUPPORT = "SUPPORT"


class ConversationStatus(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    CLOSED = "CLOSED"


class ConversationOutcome(StrEnum):
    """Desfecho de um atendimento encerrado."""

    CONVERTED = "CONVERTED"
    NOT_CONVERTED = "NOT_CONVERTED"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SenderType(StrEnum):
    BOT = "bot"
    USER = "user"
    OPERATOR = "operator"
    #: Resposta gerada por IA no atendimento. Separada de BOT porque bot e
    #: texto fixo do funil, e o painel precisa mostrar a diferenca para quem
    #: assume a conversa depois.
    AI = "ai"


class EntityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class FunnelStep(StrEnum):
    """Mensagens do funil que podem ser editadas pelo painel."""

    WELCOME = "WELCOME"
    CONSENT = "CONSENT"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    AGE_GATE = "AGE_GATE"
    AGE_REJECTED = "AGE_REJECTED"
    QUALIFICATION = "QUALIFICATION"
    INFORMATION = "INFORMATION"
    #: Primeira mensagem do atendimento por IA — a que abre a conversa antes de
    #: o modelo assumir. Editavel por campanha como qualquer outra etapa.
    AI_SUPPORT = "AI_SUPPORT"
    HUMAN_SUPPORT = "HUMAN_SUPPORT"
    FOLLOWUP = "FOLLOWUP"


#: Etapas que so existem globalmente, sem versao por campanha.
#:
#: Consentimento e age gate sao as duas telas com efeito legal. O aceite e
#: auditado por `consent_records.version`, que vem do .env: se o texto variasse
#: por campanha, dois leads gravariam a mesma versao tendo lido coisas
#: diferentes e o registro deixaria de provar o que a pessoa aceitou. O age
#: gate segue junto porque enuncia a idade minima, que tambem nao e editavel.
GLOBAL_ONLY_STEPS = {
    FunnelStep.CONSENT,
    FunnelStep.CONSENT_REQUIRED,
    FunnelStep.AGE_GATE,
    FunnelStep.AGE_REJECTED,
}


class OptionTarget(StrEnum):
    """Para onde uma opcao de qualificacao leva o lead."""

    INFORMATION = "INFORMATION"
    HUMAN_SUPPORT = "HUMAN_SUPPORT"


class AiProvider(StrEnum):
    """Provedor da integracao de IA configurada no painel.

    Dois, e nao um, porque o formato da chamada muda: o Gemini tem endpoint e
    corpo proprios, o OpenRouter segue o formato de chat completions. Quem
    administra escolhe na tela conforme a chave que tem em maos.
    """

    GEMINI = "GEMINI"
    OPENROUTER = "OPENROUTER"


class MediaType(StrEnum):
    """Tipo de midia trocada no funil e no atendimento.

    VOICE e AUDIO sao separados porque o Telegram os trata como coisas
    diferentes: voz e OGG/Opus e aparece como bolha de audio gravado, audio e
    arquivo de musica com titulo e duracao. Enviar um pelo metodo do outro
    falha ou some com a forma de onda.
    """

    PHOTO = "photo"
    VIDEO = "video"
    VOICE = "voice"
    AUDIO = "audio"
