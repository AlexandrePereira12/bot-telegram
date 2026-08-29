import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Empty, ErrorBox, Loading, Panel, money, percent } from '../components'
import { api } from '../services/api'
import type { CampaignPerformance, FunnelStep, TimeseriesPoint } from '../types'

const PERIODS = [7, 30, 90]

interface AdPerformance {
  ad_id: number
  leads: number
  conversions: number
  conversion_rate: number
}

export default function Analytics() {
  const [days, setDays] = useState(30)

  const campaigns = useQuery({
    queryKey: ['an-campaigns', days],
    queryFn: () => api<CampaignPerformance[]>(`/analytics/campaigns?days=${days}`),
  })
  const ads = useQuery({
    queryKey: ['an-ads', days],
    queryFn: () => api<AdPerformance[]>(`/analytics/ads?days=${days}`),
  })
  const series = useQuery({
    queryKey: ['an-series', days],
    queryFn: () => api<TimeseriesPoint[]>(`/analytics/timeseries?days=${days}`),
  })
  const funnel = useQuery({
    queryKey: ['an-funnel', days],
    queryFn: () => api<FunnelStep[]>(`/analytics/funnel?days=${days}`),
  })

  return (
    <>
      <h1>Analytics</h1>
      <p className="page-sub">Desempenho por campanha, anúncio e período</p>

      <div className="toolbar">
        {PERIODS.map((period) => (
          <button
            key={period}
            className={period === days ? '' : 'secondary'}
            onClick={() => setDays(period)}
          >
            {period} dias
          </button>
        ))}
      </div>

      <Panel title="Abandono por etapa">
        {funnel.isLoading && <Loading />}
        {funnel.data && (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={funnel.data}>
              <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
              <XAxis dataKey="step" stroke="#949cad" fontSize={11} />
              <YAxis stroke="#949cad" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: '#171a21',
                  border: '1px solid #2a2f3a',
                  borderRadius: 8,
                }}
              />
              <Bar dataKey="count" name="usuários" fill="#4f8cff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Panel>

      <Panel title="Conversão por campanha">
        {campaigns.isLoading && <Loading />}
        {campaigns.isError && <ErrorBox error={campaigns.error} />}
        {campaigns.data && campaigns.data.length === 0 && <Empty />}
        {campaigns.data && campaigns.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Campanha</th>
                <th>Plataforma</th>
                <th className="num">Leads</th>
                <th className="num">Conversões</th>
                <th className="num">Taxa</th>
                <th className="num">CPL</th>
                <th className="num">CPA</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.data.map((row) => (
                <tr key={row.campaign_id}>
                  <td>{row.name}</td>
                  <td>{row.platform}</td>
                  <td className="num">{row.leads}</td>
                  <td className="num">{row.conversions}</td>
                  <td className="num">{percent(row.conversion_rate)}</td>
                  <td className="num">{money(row.cpl)}</td>
                  <td className="num">{money(row.cpa)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="Conversão por anúncio">
        {ads.isLoading && <Loading />}
        {ads.data && ads.data.length === 0 && (
          <Empty text="nenhum lead atribuído a anúncio no período" />
        )}
        {ads.data && ads.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Anúncio</th>
                <th className="num">Leads</th>
                <th className="num">Conversões</th>
                <th className="num">Taxa</th>
              </tr>
            </thead>
            <tbody>
              {ads.data.map((row) => (
                <tr key={row.ad_id}>
                  <td>#{row.ad_id}</td>
                  <td className="num">{row.leads}</td>
                  <td className="num">{row.conversions}</td>
                  <td className="num">{percent(row.conversion_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="Volume diário">
        {series.data && series.data.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={series.data}>
              <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#949cad" fontSize={11} />
              <YAxis stroke="#949cad" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: '#171a21',
                  border: '1px solid #2a2f3a',
                  borderRadius: 8,
                }}
              />
              <Bar dataKey="users" name="usuários" fill="#4f8cff" radius={[4, 4, 0, 0]} />
              <Bar
                dataKey="conversions"
                name="conversões"
                fill="#35c07f"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <Empty text="sem dados no período" />
        )}
      </Panel>
    </>
  )
}
