import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'

import {
  Empty,
  ErrorBox,
  FilterChips,
  Loading,
  Pager,
  Panel,
  StatusBadge,
  datetime,
} from '../components'
import { LEAD_STATUS_LABEL, leadStatusLabel } from '../labels'
import { api } from '../services/api'
import type { Campaign, Lead, Operator } from '../types'

const PAGE_SIZE = 50

/** Perfis com `campaigns:read` no backend. Operador e suporte enxergam leads
 *  mas não campanhas: pedir a lista para eles renderia 403 e o filtro ficaria
 *  vazio sem explicação — melhor nem oferecer o controle. */
const VE_CAMPANHAS = ['ADMIN', 'MANAGER', 'ANALYST']

/** Converte o dia escolhido no calendário para instante absoluto, no fuso de
 *  quem está olhando a tela.
 *
 *  Duas correções em uma: a data pura faria o backend cortar em 00:00 (o último
 *  dia escolhido sumiria), e o texto sem fuso seria lido como UTC — com UTC-3,
 *  um lead criado às 22:00 de um dia ficava de fora do filtro "criado até"
 *  daquele mesmo dia, porque no relógio do servidor já era o dia seguinte. */
function inicioDoDia(dia: string): string {
  return new Date(`${dia}T00:00:00`).toISOString()
}

function fimDoDia(dia: string): string {
  return new Date(`${dia}T23:59:59.999`).toISOString()
}

export default function Leads() {
  const [params, setParams] = useSearchParams()

  // Os filtros vivem na URL: voltar do detalhe do lead preserva o recorte, e
  // o link pode ser colado para outra pessoa ver a mesma lista.
  const status = params.get('status') ?? ''
  const source = params.get('source') ?? ''
  const campaign = params.get('campaign') ?? ''
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const page = Math.max(Number(params.get('page') ?? 0), 0)

  function aplicar(mudancas: Record<string, string>, manterPagina = false) {
    const proximo = new URLSearchParams(params)
    Object.entries(mudancas).forEach(([chave, valor]) => {
      if (valor) proximo.set(chave, valor)
      else proximo.delete(chave)
    })
    // Trocar o filtro reinicia a paginação: a página 3 do recorte anterior
    // quase sempre não existe no recorte novo, e a tela apareceria vazia.
    if (!manterPagina) proximo.delete('page')
    setParams(proximo, { replace: true })
  }

  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Operator>('/auth/me'),
  })
  const podeVerCampanhas = VE_CAMPANHAS.includes(me.data?.role ?? '')

  const campanhas = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api<Campaign[]>('/campaigns'),
    enabled: podeVerCampanhas,
  })

  const nomePorCampanha = useMemo(() => {
    const mapa = new Map<number, string>()
    campanhas.data?.forEach((item) => mapa.set(item.id, item.name))
    return mapa
  }, [campanhas.data])

  const fontes = useMemo(
    () => [...new Set(campanhas.data?.map((item) => item.source) ?? [])].sort(),
    [campanhas.data],
  )

  const query = new URLSearchParams()
  if (status) query.set('status', status)
  if (source) query.set('source', source)
  if (campaign) query.set('campaign_id', campaign)
  if (from) query.set('created_from', inicioDoDia(from))
  if (to) query.set('created_to', fimDoDia(to))
  query.set('limit', String(PAGE_SIZE))
  query.set('offset', String(page * PAGE_SIZE))

  const leads = useQuery({
    queryKey: ['leads', status, source, campaign, from, to, page],
    queryFn: () => api<Lead[]>(`/leads?${query.toString()}`),
  })

  function campanhaLabel(id: number | null): string {
    if (id === null) return '—'
    return nomePorCampanha.get(id) ?? `#${id}`
  }

  const chips = [
    status && {
      key: 'status',
      label: `status: ${leadStatusLabel(status)}`,
      onRemove: () => aplicar({ status: '' }),
    },
    campaign && {
      key: 'campaign',
      label: `campanha: ${campanhaLabel(Number(campaign))}`,
      onRemove: () => aplicar({ campaign: '' }),
    },
    source && {
      key: 'source',
      label: `fonte: ${source}`,
      onRemove: () => aplicar({ source: '' }),
    },
    from && {
      key: 'from',
      label: `criado a partir de ${from}`,
      onRemove: () => aplicar({ from: '' }),
    },
    to && {
      key: 'to',
      label: `criado até ${to}`,
      onRemove: () => aplicar({ to: '' }),
    },
  ].filter(Boolean) as { key: string; label: string; onRemove: () => void }[]

  return (
    <>
      <h1>Leads</h1>
      <p className="page-sub">
        Cada linha é um usuário que entrou pelo bot. O filtro de campanha usa o
        last touch — a atribuição autoritativa das métricas.
      </p>

      <Panel title="Filtros">
        <div className="toolbar filters">
          <div className="field">
            <label htmlFor="filtro-status">Status</label>
            <select
              id="filtro-status"
              value={status}
              onChange={(e) => aplicar({ status: e.target.value })}
            >
              <option value="">Todos</option>
              {Object.entries(LEAD_STATUS_LABEL).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </select>
          </div>

          {podeVerCampanhas && (
            <div className="field">
              <label htmlFor="filtro-campanha">Campanha</label>
              <select
                id="filtro-campanha"
                value={campaign}
                onChange={(e) => aplicar({ campaign: e.target.value })}
              >
                <option value="">Todas</option>
                {campanhas.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="field">
            <label htmlFor="filtro-fonte">Fonte</label>
            <input
              id="filtro-fonte"
              list="fontes-conhecidas"
              value={source}
              placeholder="meta, google, organic…"
              onChange={(e) => aplicar({ source: e.target.value })}
            />
            <datalist id="fontes-conhecidas">
              {fontes.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </div>

          <div className="field">
            <label htmlFor="filtro-de">Criado de</label>
            <input
              id="filtro-de"
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => aplicar({ from: e.target.value })}
            />
          </div>

          <div className="field">
            <label htmlFor="filtro-ate">Criado até</label>
            <input
              id="filtro-ate"
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => aplicar({ to: e.target.value })}
            />
          </div>
        </div>

        <FilterChips chips={chips} onClear={() => setParams(new URLSearchParams(), { replace: true })} />
      </Panel>

      <Panel title="Resultados">
        {leads.isLoading && <Loading />}
        {leads.isError && <ErrorBox error={leads.error} />}
        {leads.data && leads.data.length === 0 && (
          <Empty
            text={
              chips.length > 0
                ? 'nenhum lead com esses filtros — remova um filtro acima para ampliar a busca'
                : 'nenhum lead registrado ainda'
            }
          />
        )}
        {leads.data && leads.data.length > 0 && (
          <>
            <table>
              <thead>
                <tr>
                  <th>Lead</th>
                  <th>Status</th>
                  <th>Fonte</th>
                  <th>Campanha (last touch)</th>
                  <th>Interesse</th>
                  <th>Criado</th>
                  <th>Última interação</th>
                  <th>Convertido</th>
                </tr>
              </thead>
              <tbody>
                {leads.data.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <Link to={`/leads/${lead.id}`}>#{lead.id}</Link>
                    </td>
                    <td>
                      <StatusBadge
                        status={lead.status}
                        label={leadStatusLabel(lead.status)}
                      />
                    </td>
                    <td>{lead.source}</td>
                    <td>{campanhaLabel(lead.last_touch_campaign_id)}</td>
                    <td>{lead.interest ?? '—'}</td>
                    <td className="muted">{datetime(lead.created_at)}</td>
                    <td className="muted">{datetime(lead.last_interaction_at)}</td>
                    <td>{datetime(lead.converted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager
              page={page}
              pageSize={PAGE_SIZE}
              count={leads.data.length}
              onChange={(proxima) =>
                aplicar({ page: proxima > 0 ? String(proxima) : '' }, true)
              }
            />
          </>
        )}
      </Panel>
    </>
  )
}
