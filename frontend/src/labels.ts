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
