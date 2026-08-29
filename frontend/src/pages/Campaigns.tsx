import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  Empty,
  ErrorBox,
  Loading,
  Panel,
  StatusBadge,
  money,
  percent,
} from '../components'
import { api } from '../services/api'
import type { Campaign, CampaignPerformance, TrackingToken } from '../types'

export default function Campaigns() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [source, setSource] = useState('meta')

  const campaigns = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api<Campaign[]>('/campaigns'),
  })
  const performance = useQuery({
    queryKey: ['campaigns-performance'],
    queryFn: () => api<CampaignPerformance[]>('/analytics/campaigns?days=30'),
  })
  const tokens = useQuery({
    queryKey: ['tokens', selected],
    queryFn: () => api<TrackingToken[]>(`/campaigns/${selected}/tokens`),
    enabled: selected !== null,
  })

  const createCampaign = useMutation({
    mutationFn: () =>
      api<Campaign>('/campaigns', {
        method: 'POST',
        body: JSON.stringify({ name, source, platform: source }),
      }),
    onSuccess: () => {
      setName('')
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['campaigns-performance'] })
    },
  })

  const createToken = useMutation({
    mutationFn: (campaignId: number) =>
      api<TrackingToken>(`/campaigns/${campaignId}/tokens`, {
        method: 'POST',
        body: JSON.stringify({ label: 'gerado pelo painel' }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tokens', selected] }),
  })

  const revokeToken = useMutation({
    mutationFn: (tokenId: number) =>
      api<TrackingToken>(`/campaigns/tokens/${tokenId}/revoke`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tokens', selected] }),
  })

  if (campaigns.isLoading || !campaigns.data) return <Loading />
  if (campaigns.isError) return <ErrorBox error={campaigns.error} />

  const rows = campaigns.data
  const perfById = new Map(performance.data?.map((p) => [p.campaign_id, p]) ?? [])

  return (
    <>
      <h1>Campanhas</h1>
      <p className="page-sub">
        Custos e ROI só aparecem quando o investimento é informado — sem esse dado
        a métrica fica em branco, nunca em zero.
      </p>

      <Panel title="Nova campanha">
        <form
          className="toolbar"
          onSubmit={(e) => {
            e.preventDefault()
            createCampaign.mutate()
          }}
        >
          <div className="field">
            <label>Nome</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label>Fonte</label>
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="meta">meta</option>
              <option value="google">google</option>
              <option value="tiktok">tiktok</option>
              <option value="outro">outro</option>
            </select>
          </div>
          <button type="submit" disabled={createCampaign.isPending || !name}>
            Criar
          </button>
        </form>
        {createCampaign.isError && <ErrorBox error={createCampaign.error} />}
      </Panel>

      <Panel title="Desempenho (30 dias)">
        {rows.length === 0 ? (
          <Empty text="nenhuma campanha cadastrada" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Campanha</th>
                <th>Fonte</th>
                <th>Status</th>
                <th className="num">Investimento</th>
                <th className="num">Leads</th>
                <th className="num">Conversões</th>
                <th className="num">Taxa</th>
                <th className="num">CPL</th>
                <th className="num">CPA</th>
                <th>Tokens</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((campaign) => {
                const perf = perfById.get(campaign.id)
                return (
                  <tr key={campaign.id}>
                    <td>{campaign.name}</td>
                    <td>{campaign.source}</td>
                    <td>
                      <StatusBadge status={campaign.status} />
                    </td>
                    <td className="num">{money(campaign.spend)}</td>
                    <td className="num">{perf?.leads ?? 0}</td>
                    <td className="num">{perf?.conversions ?? 0}</td>
                    <td className="num">{percent(perf?.conversion_rate)}</td>
                    <td className="num">{money(perf?.cpl)}</td>
                    <td className="num">{money(perf?.cpa)}</td>
                    <td>
                      <button
                        className="secondary"
                        onClick={() =>
                          setSelected(selected === campaign.id ? null : campaign.id)
                        }
                      >
                        {selected === campaign.id ? 'fechar' : 'ver'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Panel>

      {selected !== null && (
        <Panel title={`Tracking tokens · campanha ${selected}`}>
          <div className="toolbar">
            <button
              onClick={() => createToken.mutate(selected)}
              disabled={createToken.isPending}
            >
              Gerar token
            </button>
          </div>
          {tokens.isLoading && <Loading />}
          {tokens.data && tokens.data.length === 0 && (
            <Empty text="nenhum token gerado para esta campanha" />
          )}
          {tokens.data && tokens.data.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Token</th>
                  <th>Deep link</th>
                  <th>Fonte</th>
                  <th>Situação</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tokens.data.map((token) => (
                  <tr key={token.id}>
                    <td>
                      <code>{token.token}</code>
                    </td>
                    <td>
                      {token.deep_link ? (
                        <a href={token.deep_link} target="_blank" rel="noreferrer">
                          {token.deep_link}
                        </a>
                      ) : (
                        <span className="muted">bot não configurado</span>
                      )}
                    </td>
                    <td>{token.source}</td>
                    <td>
                      <span className={`badge ${token.revoked_at ? 'danger' : 'ok'}`}>
                        {token.revoked_at ? 'revogado' : 'ativo'}
                      </span>
                    </td>
                    <td>
                      {!token.revoked_at && (
                        <button
                          className="secondary"
                          onClick={() => revokeToken.mutate(token.id)}
                          disabled={revokeToken.isPending}
                        >
                          revogar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      )}
    </>
  )
}
