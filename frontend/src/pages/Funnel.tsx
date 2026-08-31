import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Empty, ErrorBox, Loading, Panel, PeriodPicker, percent } from '../components'
import { FUNNEL_STEP_HINT, funnelLabel, funnelStateLabel } from '../labels'
import { api } from '../services/api'
import type { FunnelStep } from '../types'

interface Linha extends FunnelStep {
  /** proporção sobre a primeira etapa; `null` quando não houve entrada */
  doTopo: number | null
  /** proporção sobre a etapa anterior; `null` na primeira etapa */
  daAnterior: number | null
  /** quantos deixaram de avançar em relação à etapa anterior (nunca negativo) */
  perda: number | null
  /** etapa contada por evento próprio pode superar a anterior — ver comentário */
  acimaDaAnterior: boolean
  gargalo: boolean
}

/** Monta as linhas com as duas leituras que a etapa isolada não dá: quanto
 *  sobrou do topo e quanto se perdeu da etapa imediatamente anterior.
 *
 *  Cada etapa é uma contagem independente de usuários distintos por tipo de
 *  evento (analytics_service.funnel), não um subconjunto da anterior. Uma
 *  etapa pode, portanto, ficar ACIMA da anterior — quem escolheu interesse sem
 *  concluir a qualificação, por exemplo. Tratar isso como queda negativa
 *  imprimiria "−(-12)" e barra maior que a régua; aqui vira marcação própria.
 */
function montar(steps: FunnelStep[]): Linha[] {
  const topo = steps[0]?.count ?? 0
  let anterior: number | null = null

  const linhas = steps.map((step) => {
    const perda = anterior !== null && anterior > step.count ? anterior - step.count : null
    const linha: Linha = {
      ...step,
      doTopo: topo > 0 ? step.count / topo : null,
      daAnterior: anterior !== null && anterior > 0 ? step.count / anterior : null,
      perda,
      acimaDaAnterior: anterior !== null && step.count > anterior,
      gargalo: false,
    }
    anterior = step.count
    return linha
  })

  // Gargalo é a maior perda proporcional entre etapas consecutivas, não a
  // maior perda absoluta: no topo do funil o volume é sempre maior e a etapa
  // inicial venceria a comparação em qualquer cenário.
  let pior = -1
  let indice = -1
  linhas.forEach((linha, i) => {
    if (linha.daAnterior === null || linha.perda === null) return
    const queda = 1 - linha.daAnterior
    if (queda > pior) {
      pior = queda
      indice = i
    }
  })
  if (indice >= 0 && pior > 0) linhas[indice].gargalo = true

  return linhas
}

export default function Funnel() {
  const [days, setDays] = useState(30)

  const funil = useQuery({
    queryKey: ['funnel', days],
    queryFn: () => api<FunnelStep[]>(`/analytics/funnel?days=${days}`),
  })
  // Sem parâmetro de período de propósito: o endpoint devolve a distribuição
  // do estado atual de cada usuário, que não tem recorte de tempo.
  const estados = useQuery({
    queryKey: ['states'],
    queryFn: () => api<Record<string, number>>('/analytics/states'),
  })

  if (funil.isLoading) return <Loading />
  if (funil.isError) return <ErrorBox error={funil.error} />

  const linhas = montar(funil.data ?? [])
  const topo = linhas[0]?.count ?? 0
  const semDados = linhas.every((linha) => linha.count === 0)

  const porEstado = Object.entries(estados.data ?? {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])
  const totalEstados = porEstado.reduce((soma, [, count]) => soma + count, 0)

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Funil</h1>
          <p className="page-sub">
            Usuários que alcançaram cada etapa nos últimos {days} dias. Quem já
            avançou continua contando nas etapas anteriores.
          </p>
        </div>
        <PeriodPicker days={days} onChange={setDays} />
      </div>

      <Panel title="Etapas do bot">
        {semDados ? (
          <Empty text="sem dados no período — envie /start no bot para popular o funil" />
        ) : (
          <>
            <div className="funnel">
              {linhas.map((linha) => (
                <div
                  className={`funnel-step${linha.gargalo ? ' gargalo' : ''}`}
                  key={linha.step}
                >
                  <div className="funnel-name">
                    <strong>{funnelLabel(linha.step)}</strong>
                    <span className="muted">{FUNNEL_STEP_HINT[linha.step] ?? ''}</span>
                  </div>

                  <div className="funnel-track">
                    <div
                      className="funnel-bar"
                      style={{
                        width: `${Math.min(Math.max((linha.doTopo ?? 0) * 100, 1), 100)}%`,
                      }}
                    />
                    <span className="funnel-count">{linha.count}</span>
                  </div>

                  <div className="funnel-rate">
                    <span className="num">{percent(linha.doTopo)}</span>
                    <span className="muted">do topo</span>
                  </div>

                  <div className="funnel-delta">
                    {linha.daAnterior === null ? (
                      <span className="muted">etapa inicial</span>
                    ) : linha.acimaDaAnterior ? (
                      <span className="muted" title="etapa contada por evento próprio; pode ter usuário que pulou a anterior">
                        acima da anterior
                      </span>
                    ) : linha.perda ? (
                      <>
                        <span className="perda">−{linha.perda}</span>
                        <span className="muted">
                          {percent(1 - linha.daAnterior)} de queda
                        </span>
                      </>
                    ) : (
                      <span className="muted">sem perda</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <p className="funnel-legend muted">
              Barra proporcional à primeira etapa ({topo} usuários).
              {linhas.some((linha) => linha.gargalo) && ' Etapa destacada é a de maior queda proporcional.'}
            </p>
          </>
        )}
      </Panel>

      <Panel title="Usuários por estado atual (agora)">
        {estados.isLoading && <Loading />}
        {estados.isError && <ErrorBox error={estados.error} />}
        {estados.data && porEstado.length === 0 && <Empty text="nenhum usuário registrado" />}
        {porEstado.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Estado</th>
                <th className="num">Usuários</th>
                <th className="num">Participação</th>
              </tr>
            </thead>
            <tbody>
              {porEstado.map(([state, count]) => (
                <tr key={state}>
                  <td>
                    {funnelStateLabel(state)} <span className="muted mono">{state}</span>
                  </td>
                  <td className="num">{count}</td>
                  <td className="num">{percent(count / totalEstados)}</td>
                </tr>
              ))}
              <tr>
                <td>
                  <strong>Total</strong>
                </td>
                <td className="num">
                  <strong>{totalEstados}</strong>
                </td>
                <td className="num muted">100.0%</td>
              </tr>
            </tbody>
          </table>
        )}
        <p className="muted funnel-legend">
          Estado atual de cada usuário, sem recorte de período — diferente das
          etapas acima, que contam eventos dos últimos {days} dias.{' '}
          <Link to="/leads">Ver leads</Link>
        </p>
      </Panel>
    </>
  )
}
