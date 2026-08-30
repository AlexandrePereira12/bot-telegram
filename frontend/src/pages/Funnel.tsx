import { useQuery } from '@tanstack/react-query'

import { ErrorBox, Loading, Panel } from '../components'
import { funnelLabel } from '../labels'
import { api } from '../services/api'
import type { FunnelStep } from '../types'

export default function Funnel() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['funnel'],
    queryFn: () => api<FunnelStep[]>('/analytics/funnel?days=30'),
  })
  const states = useQuery({
    queryKey: ['states'],
    queryFn: () => api<Record<string, number>>('/analytics/states'),
  })

  if (isLoading) return <Loading />
  if (isError) return <ErrorBox error={error} />

  const steps = data ?? []
  const max = Math.max(...steps.map((s) => s.count), 1)

  return (
    <>
      <h1>Funil</h1>
      <p className="page-sub">
        Contagem por etapa alcançada nos últimos 30 dias — quem já avançou continua
        contando nas etapas anteriores.
      </p>

      <Panel title="Etapas">
        {steps.every((s) => s.count === 0) && (
          <p className="muted">
            sem dados no período — envie /start no bot para popular o funil
          </p>
        )}
        {steps.map((step) => (
          <div className="funnel-row" key={step.step}>
            <span>{funnelLabel(step.step)}</span>
            <div
              className="funnel-bar"
              style={{ width: `${Math.max((step.count / max) * 100, 1)}%` }}
            />
            <span className="num">
              {step.count}
              {step.drop_from_previous !== null && step.drop_from_previous > 0 && (
                <span className="muted"> (−{step.drop_from_previous})</span>
              )}
            </span>
          </div>
        ))}
      </Panel>

      <Panel title="Usuários por estado atual">
        {states.data && (
          <table>
            <thead>
              <tr>
                <th>Estado</th>
                <th className="num">Usuários</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(states.data)
                .filter(([, count]) => count > 0)
                .map(([state, count]) => (
                  <tr key={state}>
                    <td>{state}</td>
                    <td className="num">{count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  )
}
