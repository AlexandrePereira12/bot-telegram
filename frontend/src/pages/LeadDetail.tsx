import { useQuery } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import {
  Card,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  StatusBadge,
  datetime,
} from '../components'
import {
  TIMELINE_KIND_LABEL,
  consentLabel,
  funnelStateLabel,
  leadStatusLabel,
  timelineLabel,
} from '../labels'
import { api } from '../services/api'
import type { Campaign, Operator, TimelineEntry } from '../types'

const VE_CAMPANHAS = ['ADMIN', 'MANAGER', 'ANALYST']

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

/** Detalhe da timeline em pares legíveis. `JSON.stringify` cru mostrava
 *  aspas, chaves e `null` para quem só precisa do conteúdo da mensagem. */
function detalhe(valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return ''
  if (typeof valor === 'object') return JSON.stringify(valor)
  return String(valor)
}

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  // `key === 'default'` marca a primeira entrada do histórico desta sessão:
  // link colado direto no navegador. Voltar aí sairia da aplicação.
  const veioDaListagem = location.key !== 'default'

  const lead = useQuery({
    queryKey: ['lead', id],
    queryFn: () => api<LeadDetailData>(`/leads/${id}`),
  })
  const history = useQuery({
    queryKey: ['lead-history', id],
    queryFn: () => api<TimelineEntry[]>(`/leads/${id}/history`),
  })
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Operator>('/auth/me'),
  })
  const campanhas = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api<Campaign[]>('/campaigns'),
    enabled: VE_CAMPANHAS.includes(me.data?.role ?? ''),
  })

  if (lead.isLoading) return <Loading />
  if (lead.isError) return <ErrorBox error={lead.error} />

  const data = lead.data!

  function campanha(idCampanha: number | null) {
    if (idCampanha === null) return <span className="muted">—</span>
    const nome = campanhas.data?.find((item) => item.id === idCampanha)?.name
    return nome ? (
      <>
        {nome} <span className="muted mono">#{idCampanha}</span>
      </>
    ) : (
      <>#{idCampanha}</>
    )
  }

  return (
    <>
      {/* Voltar pelo histórico e não por link fixo: os filtros da listagem
          vivem na query string e um <Link to="/leads"> os descartaria. */}
      <p>
        <button
          type="button"
          className="link"
          onClick={() => (veioDaListagem ? navigate(-1) : navigate('/leads'))}
        >
          ← voltar {veioDaListagem ? '' : 'para leads'}
        </button>
      </p>
      <h1>Lead #{data.id}</h1>
      <p className="page-sub">
        {data.telegram_first_name ?? 'sem nome'}
        {data.telegram_username ? ` · @${data.telegram_username}` : ''}
      </p>

      <div className="cards">
        <Card
          label="Status"
          value={<StatusBadge status={data.status} label={leadStatusLabel(data.status)} />}
          hint="situação comercial do lead"
        />
        <Card
          label="Estado do funil"
          value={data.current_state ? funnelStateLabel(data.current_state) : '—'}
          hint="onde o usuário parou na conversa com o bot"
        />
        <Card
          label="Consentimento"
          value={data.consent_status ? consentLabel(data.consent_status) : '—'}
          hint={data.age_confirmed ? 'idade confirmada' : 'idade não confirmada'}
        />
        <Card label="Fonte" value={data.source} hint="origem declarada na entrada" />
        <Card label="Interesse" value={data.interest ?? '—'} hint="escolha na qualificação" />
      </div>

      <Panel title="Atribuição">
        <table>
          <tbody>
            <tr>
              <th>Campanha de last touch (autoritativa)</th>
              <td>{campanha(data.last_touch_campaign_id)}</td>
            </tr>
            <tr>
              <th>Campanha de first touch (histórico)</th>
              <td>{campanha(data.first_touch_campaign_id)}</td>
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
        <p className="muted funnel-legend">
          Métricas e filtros por campanha usam o last touch.{' '}
          {/* Sem campanha atribuída o link abriria a lista inteira prometendo
              "mesma campanha" — melhor não oferecê-lo. */}
          {data.last_touch_campaign_id !== null && (
            <Link to={`/leads?campaign=${data.last_touch_campaign_id}`}>
              Ver leads da mesma campanha
            </Link>
          )}
        </p>
      </Panel>

      <Panel title="Linha do tempo">
        {history.isLoading && <Loading />}
        {history.isError && <ErrorBox error={history.error} />}
        {history.data && history.data.length === 0 && (
          <Empty text="nenhum evento registrado para este lead" />
        )}
        {history.data?.map((entry, index) => {
          const pares = Object.entries(entry.detail ?? {}).filter(
            ([, valor]) => detalhe(valor) !== '',
          )
          return (
            <div className="timeline-item" key={index}>
              <div className="timeline-head">
                <strong>{timelineLabel(entry.kind, entry.label)}</strong>
                <span className="badge">{TIMELINE_KIND_LABEL[entry.kind] ?? entry.kind}</span>
                <span className="muted timeline-when">{datetime(entry.at)}</span>
              </div>
              {pares.length > 0 && (
                <dl className="timeline-detail">
                  {pares.map(([chave, valor]) => (
                    <div key={chave}>
                      <dt>{chave}</dt>
                      <dd>{detalhe(valor)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          )
        })}
      </Panel>
    </>
  )
}
