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

import {
  Empty,
  ErrorBox,
  Loading,
  Panel,
  PeriodPicker,
  money,
  percent,
} from '../components'
import { funnelLabel } from '../labels'
import { api } from '../services/api'
import { useChartTokens } from '../theme'
import type { CampaignPerformance, FunnelStep, TimeseriesPoint } from '../types'

interface AdPerformance {
  ad_id: number
  leads: number
  conversions: number
  conversion_rate: number
}

/** O eixo não comporta a data ISO inteira; dia/mês basta para ler a série. */
function diaCurto(valor: string): string {
  const [, mes, dia] = valor.split('-')
  return mes && dia ? `${dia}/${mes}` : valor
}

export default function Analytics() {
  const [days, setDays] = useState(30)
  const chart = useChartTokens()

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
      <div className="section-head">
        <div>
          <h1>Analytics</h1>
          <p className="page-sub">Desempenho por campanha, anúncio e período</p>
        </div>
        {/* Mesmo controle do Dashboard e do Funil: o seletor de período muda
            de forma entre as telas fazia parecer que o recorte também mudava. */}
        <PeriodPicker days={days} onChange={setDays} />
      </div>

      <Panel title="Abandono por etapa">
        {funnel.isLoading && <Loading />}
        {funnel.data && (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={funnel.data}>
              <defs>
                <linearGradient id="gradBarraFunil" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chart.serie1} stopOpacity={1} />
                  <stop offset="100%" stopColor={chart.serie1} stopOpacity={0.55} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={chart.grid} vertical={false} />
              <XAxis
                dataKey="step"
                stroke={chart.grid}
                tick={{ fill: chart.axis, fontSize: 11 }}
                tickLine={false}
                tickFormatter={funnelLabel}
                interval={0}
              />
              <YAxis
                stroke={chart.grid}
                tick={{ fill: chart.axis, fontSize: 11 }}
                tickLine={false}
                allowDecimals={false}
                width={38}
              />
              <Tooltip
                contentStyle={chart.tooltip}
                cursor={{ fill: chart.grid, fillOpacity: 0.35 }}
              />
              <Bar
                dataKey="count"
                name="usuários"
                fill="url(#gradBarraFunil)"
                radius={[4, 4, 0, 0]}
                maxBarSize={44}
              />
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
              <defs>
                <linearGradient id="gradBarraUsuarios" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chart.serie1} stopOpacity={1} />
                  <stop offset="100%" stopColor={chart.serie1} stopOpacity={0.55} />
                </linearGradient>
                <linearGradient id="gradBarraConversoes" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chart.serie2} stopOpacity={1} />
                  <stop offset="100%" stopColor={chart.serie2} stopOpacity={0.55} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={chart.grid} vertical={false} />
              <XAxis
                dataKey="day"
                stroke={chart.grid}
                tick={{ fill: chart.axis, fontSize: 11 }}
                tickLine={false}
                tickFormatter={diaCurto}
                minTickGap={16}
              />
              <YAxis
                stroke={chart.grid}
                tick={{ fill: chart.axis, fontSize: 11 }}
                tickLine={false}
                allowDecimals={false}
                width={38}
              />
              <Tooltip
                contentStyle={chart.tooltip}
                cursor={{ fill: chart.grid, fillOpacity: 0.35 }}
              />
              <Bar
                dataKey="users"
                name="usuários"
                fill="url(#gradBarraUsuarios)"
                radius={[4, 4, 0, 0]}
                maxBarSize={28}
              />
              <Bar
                dataKey="conversions"
                name="conversões"
                fill="url(#gradBarraConversoes)"
                radius={[4, 4, 0, 0]}
                maxBarSize={28}
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
