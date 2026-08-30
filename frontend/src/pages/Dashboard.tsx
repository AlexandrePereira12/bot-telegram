import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Card, ErrorBox, Loading, Panel, duration, percent } from '../components'
import { api } from '../services/api'
import { useChartTokens } from '../theme'
import type { Overview, TimeseriesPoint } from '../types'

/** O eixo não comporta a data ISO inteira; dia/mês basta para ler a série. */
function diaCurto(valor: string): string {
  const [, mes, dia] = valor.split('-')
  return mes && dia ? `${dia}/${mes}` : valor
}

export default function Dashboard() {
  const chart = useChartTokens()
  const overview = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<Overview>('/analytics/overview?days=30'),
  })
  const series = useQuery({
    queryKey: ['timeseries'],
    queryFn: () => api<TimeseriesPoint[]>('/analytics/timeseries?days=30'),
  })

  if (overview.isLoading) return <Loading />
  if (overview.isError) return <ErrorBox error={overview.error} />

  const data = overview.data!

  return (
    <>
      <h1>Dashboard</h1>
      <p className="page-sub">Últimos {data.period_days} dias</p>

      <div className="cards">
        <Card label="Usuários" value={data.users} />
        <Card label="Leads" value={data.leads} />
        <Card label="Qualificados" value={data.qualified} />
        <Card label="Conversões" value={data.conversions} />
        <Card label="Taxa de conversão" value={percent(data.conversion_rate)} />
        <Card label="Aguardando atendimento" value={data.awaiting_support} />
        <Card
          label="Tempo até conversão"
          value={duration(data.avg_seconds_to_conversion)}
        />
      </div>

      <Panel title="Usuários e conversões por dia">
        {series.isLoading && <Loading />}
        {series.data && series.data.length === 0 && (
          <p className="muted">
            sem eventos no período — envie /start no bot para gerar dados
          </p>
        )}
        {series.data && series.data.length > 0 && (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series.data}>
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
              <Tooltip contentStyle={chart.tooltip} cursor={{ stroke: chart.grid }} />
              <Line
                type="monotone"
                dataKey="users"
                name="usuários"
                stroke={chart.serie1}
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="conversions"
                name="conversões"
                stroke={chart.serie2}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Panel>
    </>
  )
}
