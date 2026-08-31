/** Rótulos das etapas do funil (`/analytics/funnel`). O backend devolve a
 *  chave crua — o mapa vive aqui para o funil e o gráfico de Analytics não
 *  divergirem no nome da mesma etapa. */
export const FUNNEL_LABEL: Record<string, string> = {
  entradas: 'Entradas',
  consentimento: 'Consentimento',
  idade_confirmada: 'Idade confirmada',
  qualificacao: 'Qualificação',
  interesse: 'Interesse',
  atendimento: 'Atendimento',
  conversao: 'Conversão',
}

export function funnelLabel(step: string): string {
  return FUNNEL_LABEL[step] ?? step
}

/** Rótulos dos status de lead. O backend devolve o código cru (`LeadStatus`);
 *  o filtro, a tabela e o badge precisam usar o mesmo texto — dropdown em
 *  português com coluna em inglês foi a origem da leitura confusa da tela. */
export const LEAD_STATUS_LABEL: Record<string, string> = {
  NEW: 'Novo',
  QUALIFYING: 'Em qualificação',
  QUALIFIED: 'Qualificado',
  IN_SUPPORT: 'Em atendimento',
  CONVERTED: 'Convertido',
  LOST: 'Perdido',
}

export function leadStatusLabel(status: string): string {
  return LEAD_STATUS_LABEL[status] ?? status
}

/** Rótulos dos estados da FSM do bot (`FunnelState`), usados no painel
 *  "usuários por estado" e no detalhe do lead. */
export const FUNNEL_STATE_LABEL: Record<string, string> = {
  NEW: 'Novo',
  WELCOME: 'Boas-vindas',
  CONSENT: 'Consentimento',
  AGE_GATE: 'Verificação de idade',
  QUALIFICATION: 'Qualificação',
  INFORMATION: 'Informação',
  HUMAN_SUPPORT: 'Atendimento humano',
  CONVERTED: 'Convertido',
  EXIT: 'Saída',
}

export function funnelStateLabel(state: string): string {
  return FUNNEL_STATE_LABEL[state] ?? state
}

/** Consentimento (`ConsentStatus`) — usado no detalhe do lead. */
export const CONSENT_LABEL: Record<string, string> = {
  PENDING: 'Pendente',
  ACCEPTED: 'Aceito',
  REJECTED: 'Recusado',
  REVOKED: 'Revogado',
}

export function consentLabel(status: string): string {
  return CONSENT_LABEL[status] ?? status
}

/** Descrição de cada etapa do funil. O nome sozinho não diz qual evento é
 *  contado, e sem isso a leitura da queda entre etapas vira chute. */
export const FUNNEL_STEP_HINT: Record<string, string> = {
  entradas: 'Usuários que enviaram /start',
  consentimento: 'Aceitaram a política de dados',
  idade_confirmada: 'Confirmaram ser maiores de idade',
  qualificacao: 'Concluíram o questionário de qualificação',
  interesse: 'Escolheram um interesse',
  atendimento: 'Pediram atendimento humano',
  conversao: 'Registraram conversão',
}

/** Eventos do bot (`EventType`) na timeline do lead. O código cru descreve o
 *  que aconteceu para quem conhece a FSM; a timeline é lida por quem atende. */
export const EVENT_LABEL: Record<string, string> = {
  USER_STARTED: 'Entrou no bot',
  WELCOME_SENT: 'Boas-vindas enviadas',
  CONSENT_VIEWED: 'Viu o termo de consentimento',
  CONSENT_ACCEPTED: 'Aceitou o consentimento',
  CONSENT_REJECTED: 'Recusou o consentimento',
  CONSENT_REVOKED: 'Revogou o consentimento',
  AGE_CONFIRMED: 'Confirmou a idade',
  AGE_REJECTED: 'Reprovado na verificação de idade',
  QUALIFICATION_STARTED: 'Iniciou a qualificação',
  QUALIFICATION_COMPLETED: 'Concluiu a qualificação',
  INTEREST_SELECTED: 'Escolheu um interesse',
  FAQ_OPENED: 'Abriu o FAQ',
  HUMAN_SUPPORT_REQUESTED: 'Pediu atendimento humano',
  HUMAN_SUPPORT_ASSIGNED: 'Atendimento atribuído',
  HUMAN_SUPPORT_RELEASED: 'Atendimento devolvido à automação',
  HUMAN_SUPPORT_CLOSED: 'Atendimento encerrado',
  FUNNEL_REOPENED: 'Funil reaberto',
  MESSAGE_SENT: 'Mensagem enviada',
  MESSAGE_RECEIVED: 'Mensagem recebida',
  FOLLOWUP_SCHEDULED: 'Follow-up agendado',
  FOLLOWUP_SENT: 'Follow-up enviado',
  CONVERSION: 'Conversão',
  USER_BLOCKED: 'Usuário bloqueou o bot',
}

/** Rótulo de uma entrada da timeline. Mensagens chegam como
 *  `direcao:remetente` (ex.: `inbound:user`), não como `EventType`. */
export function timelineLabel(kind: string, label: string): string {
  if (kind === 'message') {
    const [, remetente] = label.split(':')
    const de: Record<string, string> = {
      user: 'Mensagem do usuário',
      bot: 'Mensagem do bot',
      operator: 'Mensagem do operador',
    }
    return de[remetente] ?? label
  }
  if (kind === 'conversion') return `Conversão (${label})`
  return EVENT_LABEL[label] ?? label
}

export const TIMELINE_KIND_LABEL: Record<string, string> = {
  event: 'evento',
  message: 'mensagem',
  conversion: 'conversão',
}
