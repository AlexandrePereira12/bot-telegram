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
import type { Overview, TimeseriesPoint } from '../types'

export default function Dashboard() {
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
              <Line
                type="monotone"
                dataKey="users"
                name="usuários"
                stroke="#4f8cff"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="conversions"
                name="conversões"
                stroke="#35c07f"
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
