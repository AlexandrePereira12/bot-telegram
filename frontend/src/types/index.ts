export interface Operator {
  id: number
  email: string
  full_name: string | null
  role: 'ADMIN' | 'MANAGER' | 'OPERATOR' | 'ANALYST' | 'SUPPORT'
  is_active: boolean
}

/** Visão administrativa do operador (`/operators`), separada de `Operator`
 *  para não ampliar o que `/auth/me` devolve. */
export interface OperatorAdmin {
  id: number
  email: string
  full_name: string | null
  role: Operator['role']
  is_active: boolean
  /** true enquanto o perfil que exige 2FA ainda não cadastrou o autenticador */
  totp_pending: boolean
  created_at: string
}

export interface OperatorCreated extends OperatorAdmin {
  /** preenchida só quando o servidor gerou a senha; exibida uma única vez */
  generated_password: string | null
}

export interface Overview {
  period_days: number
  users: number
  leads: number
  qualified: number
  conversions: number
  conversion_rate: number
  awaiting_support: number
  avg_seconds_to_conversion: number | null
}

export interface FunnelStep {
  step: string
  count: number
  drop_from_previous: number | null
}

export interface CampaignPerformance {
  campaign_id: number
  name: string
  source: string
  platform: string
  spend: number | null
  impressions: number | null
  clicks: number | null
  leads: number
  conversions: number
  conversion_rate: number
  cpl: number | null
  cpa: number | null
}

export interface Campaign {
  id: number
  name: string
  source: string
  platform: string
  external_id: string | null
  status: 'ACTIVE' | 'PAUSED' | 'ARCHIVED'
  spend: number | null
  impressions: number | null
  clicks: number | null
  created_at: string
}

export interface TrackingToken {
  id: number
  token: string
  campaign_id: number
  source: string
  label: string | null
  revoked_at: string | null
  created_at: string
  deep_link: string | null
}

export interface Lead {
  id: number
  telegram_user_id: number
  status: string
  source: string
  interest: string | null
  first_touch_campaign_id: number | null
  last_touch_campaign_id: number | null
  created_at: string
  converted_at: string | null
  last_interaction_at: string | null
}

export interface TimelineEntry {
  kind: 'event' | 'message' | 'conversion'
  at: string
  label: string
  detail: Record<string, unknown> | null
}

export type ConversationOutcome = 'CONVERTED' | 'NOT_CONVERTED'

export interface Conversation {
  id: number
  telegram_user_id: number
  status: 'OPEN' | 'ASSIGNED' | 'CLOSED'
  assigned_to: number | null
  started_at: string | null
  ended_at: string | null
  created_at: string
  /** null enquanto aberta ou apenas devolvida para a automação */
  outcome: ConversationOutcome | null
  outcome_reason: string | null
  closed_by_operator_id: number | null
}

export interface Message {
  id: number
  conversation_id: number
  media_path: string | null
  media_type: 'photo' | 'video' | null
  direction: 'inbound' | 'outbound'
  sender_type: 'bot' | 'user' | 'operator'
  sender_id: number | null
  message_type: string
  content: string | null
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
  telegram_username: string | null
  lead_id: number | null
}

export interface TimeseriesPoint {
  day: string
  users: number
  conversions: number
}

export type FunnelStepKey =
  | 'WELCOME'
  | 'CONSENT'
  | 'CONSENT_REQUIRED'
  | 'AGE_GATE'
  | 'AGE_REJECTED'
  | 'QUALIFICATION'
  | 'INFORMATION'
  | 'HUMAN_SUPPORT'
  | 'FOLLOWUP'

export interface FunnelStepContent {
  step: FunnelStepKey
  body: string
  media_path: string | null
  media_type: 'photo' | 'video' | null
  /** de onde veio o texto exibido */
  origin: 'campanha' | 'global' | 'codigo'
  editable_per_campaign: boolean
}

export interface QualificationOption {
  id: number
  campaign_id: number | null
  key: string
  label: string
  target: 'INFORMATION' | 'HUMAN_SUPPORT'
  sort_order: number
  is_active: boolean
  /** resposta própria; vazio faz cair na mensagem genérica da etapa */
  response_body: string | null
  response_media_path: string | null
  response_media_type: 'photo' | 'video' | null
}

export interface MediaUpload {
  media_path: string
  media_type: 'photo' | 'video'
  size_bytes: number
}
