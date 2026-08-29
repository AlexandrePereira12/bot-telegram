import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Empty, ErrorBox, Loading, Panel, StatusBadge, datetime } from '../components'
import { api } from '../services/api'
import type { Lead } from '../types'

const STATUSES = ['', 'NEW', 'QUALIFYING', 'QUALIFIED', 'IN_SUPPORT', 'CONVERTED', 'LOST']

export default function Leads() {
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')

  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (source) params.set('source', source)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['leads', status, source],
    queryFn: () => api<Lead[]>(`/leads?${params.toString()}`),
  })

  return (
    <>
      <h1>Leads</h1>
      <p className="page-sub">
        Filtro por campanha usa o last touch — a atribuição autoritativa das métricas.
      </p>

      <Panel title="Filtros">
        <div className="toolbar">
          <div className="field">
            <label>Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s || 'todos'}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Fonte</label>
            <input
              value={source}
              placeholder="meta, google, organic…"
              onChange={(e) => setSource(e.target.value)}
            />
          </div>
        </div>
      </Panel>

      <Panel title="Resultados">
        {isLoading && <Loading />}
        {isError && <ErrorBox error={error} />}
        {data && data.length === 0 && <Empty text="nenhum lead com esses filtros" />}
        {data && data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Status</th>
                <th>Fonte</th>
                <th>Interesse</th>
                <th>First touch</th>
                <th>Last touch</th>
                <th>Criado</th>
                <th>Convertido</th>
              </tr>
            </thead>
            <tbody>
              {data.map((lead) => (
                <tr key={lead.id}>
                  <td>
                    <Link to={`/leads/${lead.id}`}>#{lead.id}</Link>
                  </td>
                  <td>
                    <StatusBadge status={lead.status} />
                  </td>
                  <td>{lead.source}</td>
                  <td>{lead.interest ?? '—'}</td>
                  <td className="muted">{lead.first_touch_campaign_id ?? '—'}</td>
                  <td>{lead.last_touch_campaign_id ?? '—'}</td>
                  <td className="muted">{datetime(lead.created_at)}</td>
                  <td>{datetime(lead.converted_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  )
}
