"""Schemas de entrada e saida da API.

Regra de fronteira: nenhum modelo ORM e serializado direto para o cliente —
tudo passa por um schema explicito, para nunca vazar coluna interna
(password_hash, totp_secret, ip_hash).
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)

from app.core.enums import (
    ConversationOutcome,
    ConversationStatus,
    EntityStatus,
    EventType,
    FunnelState,
    FunnelStep,
    LeadStatus,
    MediaType,
    MessageDirection,
    OperatorRole,
    OptionTarget,
    SenderType,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    totp_code: str | None = Field(default=None, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class EnrollmentResponse(BaseModel):
    """Primeiro acesso de perfil que exige 2FA.

    Devolvido no lugar dos tokens enquanto o cadastro do 2FA esta pendente. A
    `otpauth_uri` vira QR no navegador; `secret` e so o fallback de digitacao
    manual. Nenhum dos dois volta a ser exposto depois de confirmado.
    """

    enrollment_required: Literal[True] = True
    enrollment_token: str
    otpauth_uri: str
    secret: str
    expires_in: int


class Enroll2FARequest(BaseModel):
    enrollment_token: str
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str


class OperatorOut(ORMModel):
    id: int
    email: str
    full_name: str | None
    role: OperatorRole
    is_active: bool


# ------------------------------------------------------- operadores (admin)
class OperatorCreate(BaseModel):
    """Cadastro de operador pelo dashboard.

    `password` e opcional de proposito: sem ela o servidor gera uma senha
    forte e a devolve uma unica vez, igual ao `create-admin` da CLI. Isso
    evita senha fraca escolhida no calor do cadastro.
    """

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=128)
    role: OperatorRole
    password: str | None = Field(default=None, min_length=8, max_length=128)


class OperatorAdminOut(ORMModel):
    """Visao administrativa do operador.

    Separada de `OperatorOut` (usada em /auth/me) para nao ampliar o que a
    rota de sessao devolve. `totp_pending` diz se o operador ainda precisa
    cadastrar o autenticador no primeiro login.
    """

    id: int
    email: str
    full_name: str | None
    role: OperatorRole
    is_active: bool
    totp_pending: bool
    created_at: datetime


class OperatorUpdate(BaseModel):
    """Alteracao de operador pelo painel.

    Todos os campos sao opcionais: o cliente manda so o que mudou. `email` e
    `password` ficam de fora de proposito — trocar identidade ou credencial
    de outra pessoa e outra operacao, com outro risco.
    """

    full_name: str | None = Field(default=None, max_length=128)
    role: OperatorRole | None = None
    is_active: bool | None = None


class OperatorCreated(OperatorAdminOut):
    """Resposta do cadastro.

    `generated_password` so vem preenchida quando o servidor gerou a senha —
    e essa e a unica vez que ela sai do servidor. Nunca vai para a auditoria.
    """

    generated_password: str | None = None


# ------------------------------------------------------------------ campanhas
class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source: str = Field(default="unknown", max_length=64)
    platform: str = Field(default="unknown", max_length=64)
    external_id: str | None = Field(default=None, max_length=128)
    spend: float | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=64)
    status: EntityStatus | None = None
    spend: float | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)


class CampaignOut(ORMModel):
    id: int
    name: str
    source: str
    platform: str
    external_id: str | None
    status: EntityStatus
    spend: float | None
    impressions: int | None
    clicks: int | None
    created_at: datetime


class AdSetCreate(BaseModel):
    campaign_id: int
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = Field(default=None, max_length=128)


class AdSetOut(ORMModel):
    id: int
    campaign_id: int
    name: str
    external_id: str | None
    status: EntityStatus


class AdCreate(BaseModel):
    ad_set_id: int
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = Field(default=None, max_length=128)
    creative: str | None = Field(default=None, max_length=512)


class AdOut(ORMModel):
    id: int
    ad_set_id: int
    name: str
    creative: str | None
    status: EntityStatus


class TrackingTokenCreate(BaseModel):
    ad_set_id: int | None = None
    ad_id: int | None = None
    source: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=255)


class TrackingTokenOut(ORMModel):
    id: int
    token: str
    campaign_id: int
    ad_set_id: int | None
    ad_id: int | None
    source: str
    label: str | None
    revoked_at: datetime | None
    created_at: datetime


class TrackingTokenWithLink(TrackingTokenOut):
    deep_link: str | None = None


# ---------------------------------------------------------------------- leads
class LeadOut(ORMModel):
    id: int
    telegram_user_id: int
    status: LeadStatus
    source: str
    interest: str | None
    first_touch_campaign_id: int | None
    last_touch_campaign_id: int | None
    created_at: datetime
    converted_at: datetime | None
    last_interaction_at: datetime | None


class LeadDetail(LeadOut):
    telegram_username: str | None = None
    telegram_first_name: str | None = None
    current_state: FunnelState | None = None
    consent_status: str | None = None
    age_confirmed: bool | None = None


class TimelineEntry(BaseModel):
    kind: Literal["event", "message", "conversion"]
    at: datetime
    label: str
    detail: dict[str, Any] | None = None


class EventOut(ORMModel):
    id: int
    event_type: EventType
    telegram_user_id: int | None
    lead_id: int | None
    campaign_id: int | None
    event_metadata: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class EventCreate(BaseModel):
    """Ingestao manual/externa de evento. Exige chave de idempotencia."""

    event_type: EventType
    lead_id: int | None = None
    telegram_user_id: int | None = None
    campaign_id: int | None = None
    metadata: dict[str, Any] | None = None
    idempotency_key: str = Field(min_length=8, max_length=255)


# --------------------------------------------------------------- conversas
class ConversationOut(ORMModel):
    id: int
    telegram_user_id: int
    status: ConversationStatus
    assigned_to: int | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    outcome: ConversationOutcome | None = None
    outcome_reason: str | None = None
    closed_by_operator_id: int | None = None


class MessageOut(ORMModel):
    id: int
    conversation_id: int
    media_id: int | None = None
    media_type: MediaType | None = None
    direction: MessageDirection
    sender_type: SenderType
    sender_id: int | None
    message_type: str
    content: str | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []
    telegram_username: str | None = None
    lead_id: int | None = None


class OperatorReply(BaseModel):
    """Resposta do operador. Texto vazio e aceito quando ha midia anexada."""

    content: str = Field(default="", max_length=4000)
    media_id: int | None = Field(default=None, ge=1)
    media_type: MediaType | None = None

    @model_validator(mode="after")
    def _exige_conteudo(self) -> "OperatorReply":
        if not self.content.strip() and self.media_id is None:
            raise ValueError("informe um texto ou anexe um arquivo")
        return self


class CloseRequest(BaseModel):
    """Encerramento do atendimento com desfecho."""

    outcome: ConversationOutcome
    reason: str | None = Field(default=None, max_length=255)
    value: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    #: Ultima mensagem enviada ao lead junto do encerramento. Opcional: fechar
    #: um atendimento que o lead abandonou nao deve obrigar a escrever nada.
    farewell: str | None = Field(default=None, max_length=4000)


# -------------------------------------------------------------------- webhook
class ConversionWebhook(BaseModel):
    external_id: str = Field(min_length=1, max_length=128)
    lead_id: int | None = None
    telegram_id: int | None = None
    conversion_type: str = Field(default="signup", max_length=64)
    value: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    metadata: dict[str, Any] | None = None


# ------------------------------------------------------------------- health
class ComponentHealth(BaseModel):
    status: Literal["ok", "error", "disabled"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    company: str
    environment: str
    components: dict[str, ComponentHealth]


# --------------------------------------------------------- conteudo do funil
def _validate_compliance(value: str) -> str:
    """Barra promessa de ganho na escrita.

    Enquanto os textos viviam no codigo, um teste varria o modulo e garantia
    isso. Editaveis pelo painel, a garantia tem de acontecer aqui — senao
    qualquer operador escreve o que a regra de compliance proibe.
    """
    from app.services.compliance import ComplianceError, assert_compliant

    try:
        return assert_compliant(value)
    except ComplianceError as exc:
        raise ValueError(str(exc)) from exc


CompliantText = Annotated[str, AfterValidator(_validate_compliance)]


class FunnelContentIn(BaseModel):
    step: FunnelStep
    body: CompliantText = Field(min_length=1, max_length=4000)
    media_id: int | None = Field(default=None, ge=1)
    media_type: MediaType | None = None


class FunnelContentOut(ORMModel):
    id: int
    campaign_id: int | None
    step: FunnelStep
    body: str
    media_id: int | None
    media_type: MediaType | None
    updated_at: datetime


class ResolvedStepOut(BaseModel):
    """Como a etapa fica para uma campanha, com a origem do texto."""

    step: FunnelStep
    body: str
    media_id: int | None = None
    media_type: MediaType | None = None
    origin: Literal["campanha", "global", "codigo"]
    editable_per_campaign: bool


class QualificationOptionIn(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    label: CompliantText = Field(min_length=1, max_length=128)
    target: OptionTarget = OptionTarget.INFORMATION
    sort_order: int = Field(default=0, ge=0, le=999)
    is_active: bool = True
    #: Resposta que o bot envia ao escolherem esta opcao. Vazio faz cair na
    #: mensagem generica da etapa INFORMATION.
    response_body: CompliantText | None = Field(default=None, max_length=4000)
    response_media_id: int | None = Field(default=None, ge=1)
    response_media_type: MediaType | None = None


class QualificationOptionOut(ORMModel):
    id: int
    campaign_id: int | None
    key: str
    label: str
    target: OptionTarget
    sort_order: int
    is_active: bool
    response_body: str | None = None
    response_media_id: int | None = None
    response_media_type: MediaType | None = None


class MediaUploadOut(BaseModel):
    """Midia recem-gravada. `media_id` e a referencia usada em toda parte —
    caminho de arquivo deixou de existir quando os bytes foram para o banco."""

    media_id: int
    media_type: MediaType
    size_bytes: int
