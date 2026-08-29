import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { Card, Empty, ErrorBox, Loading, Panel, StatusBadge, datetime } from '../components'
import { api } from '../services/api'
import type { TimelineEntry } from '../types'

interface LeadDetailData {
  id: number
  status: string
  source: string
  interest: string | null
  first_touch_campaign_id: number | null
  last_touch_campaign_id: number | null
  created_at: string
  converted_at: string | null
  telegram_username: string | null
  telegram_first_name: string | null
  current_state: string | null
  consent_status: string | null
  age_confirmed: boolean | null
}

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>()

  const lead = useQuery({
    queryKey: ['lead', id],
    queryFn: () => api<LeadDetailData>(`/leads/${id}`),
  })
  const history = useQuery({
    queryKey: ['lead-history', id],
    queryFn: () => api<TimelineEntry[]>(`/leads/${id}/history`),
  })

  if (lead.isLoading) return <Loading />
  if (lead.isError) return <ErrorBox error={lead.error} />

  const data = lead.data!

  return (
    <>
      <p>
        <Link to="/leads">← voltar para leads</Link>
      </p>
      <h1>Lead #{data.id}</h1>
      <p className="page-sub">
        {data.telegram_first_name ?? 'sem nome'}
        {data.telegram_username ? ` · @${data.telegram_username}` : ''}
      </p>

      <div className="cards">
        <Card label="Status" value={<StatusBadge status={data.status} />} />
        <Card label="Estado do funil" value={data.current_state ?? '—'} />
        <Card label="Consentimento" value={data.consent_status ?? '—'} />
        <Card label="Idade confirmada" value={data.age_confirmed ? 'sim' : 'não'} />
        <Card label="Fonte" value={data.source} />
        <Card label="Interesse" value={data.interest ?? '—'} />
      </div>

      <Panel title="Atribuição">
        <table>
          <tbody>
            <tr>
              <th>First touch (histórico)</th>
              <td>{data.first_touch_campaign_id ?? '—'}</td>
            </tr>
            <tr>
              <th>Last touch (autoritativo)</th>
              <td>{data.last_touch_campaign_id ?? '—'}</td>
            </tr>
            <tr>
              <th>Criado em</th>
              <td>{datetime(data.created_at)}</td>
            </tr>
            <tr>
              <th>Convertido em</th>
              <td>{datetime(data.converted_at)}</td>
            </tr>
          </tbody>
        </table>
      </Panel>

      <Panel title="Timeline (eventos, mensagens e conversões)">
        {history.isLoading && <Loading />}
        {history.data && history.data.length === 0 && <Empty />}
        {history.data?.map((entry, index) => (
          <div className="timeline-item" key={index}>
            <div>
              <span className="badge">{entry.kind}</span> <strong>{entry.label}</strong>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              {datetime(entry.at)}
            </div>
            {entry.detail && Object.keys(entry.detail).length > 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {JSON.stringify(entry.detail)}
              </div>
            )}
          </div>
        ))}
      </Panel>
    </>
  )
}
