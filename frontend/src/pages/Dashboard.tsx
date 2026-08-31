import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  Card,
  ErrorBox,
  Loading,
  Panel,
  PeriodPicker,
  duration,
  percent,
} from '../components'
import { api } from '../services/api'
import { useChartTokens } from '../theme'
import type { Overview, TimeseriesPoint } from '../types'

/** O eixo não comporta a data ISO inteira; dia/mês basta para ler a série. */
function diaCurto(valor: string): string {
  const [, mes, dia] = valor.split('-')
  return mes && dia ? `${dia}/${mes}` : valor
}

/** Proporção entre duas contagens do mesmo período. Base zero devolve `null`
 *  para o cartão exibir "—" em vez de 0%, que leria como "ninguém avançou"
 *  quando na verdade não houve entrada nenhuma. */
function taxa(parte: number, total: number): number | null {
  return total > 0 ? parte / total : null
}

export default function Dashboard() {
  const [days, setDays] = useState(30)
  const chart = useChartTokens()

  const overview = useQuery({
    queryKey: ['overview', days],
    queryFn: () => api<Overview>(`/analytics/overview?days=${days}`),
  })
  const series = useQuery({
    queryKey: ['timeseries', days],
    queryFn: () => api<TimeseriesPoint[]>(`/analytics/timeseries?days=${days}`),
  })

  if (overview.isLoading) return <Loading />
  if (overview.isError) return <ErrorBox error={overview.error} />

  const data = overview.data!
  const vazio = data.users === 0 && data.leads === 0

  // Data de corte do link para a listagem. Sem ela o cartão contaria o período
  // e a lista mostraria tudo desde sempre — dois números para o mesmo rótulo.
  const desde = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Dashboard</h1>
          <p className="page-sub">
            Visão geral dos últimos {data.period_days} dias. Os indicadores de
            aquisição contam o período; o de operação conta agora.
          </p>
        </div>
        <PeriodPicker days={days} onChange={setDays} />
      </div>

      {vazio && (
        <Panel title="Sem dados no período">
          <p className="muted">
            Nenhum usuário entrou no bot nos últimos {data.period_days} dias. Envie
            /start no bot ou aumente o período para ver os indicadores.
          </p>
        </Panel>
      )}

      <h2 className="group-title">
        Aquisição <span className="muted">· últimos {data.period_days} dias</span>
      </h2>
      <div className="cards">
        <Card
          label="Usuários"
          value={data.users}
          hint="entraram no bot no período"
        />
        <Card
          label="Leads"
          value={data.leads}
          hint="usuários que viraram lead"
          to={`/leads?from=${desde}`}
        />
        {/* Sem link: `qualified` no backend soma QUALIFIED, IN_SUPPORT e
            CONVERTED, e a listagem filtra um status por vez — o clique abriria
            uma lista menor que o número do cartão. */}
        <Card
          label="Qualificados"
          value={data.qualified}
          hint={
            data.leads > 0
              ? `${percent(taxa(data.qualified, data.leads))} dos leads · inclui em atendimento e convertidos`
              : 'sem leads no período'
          }
        />
      </div>

      <h2 className="group-title">
        Resultado <span className="muted">· últimos {data.period_days} dias</span>
      </h2>
      <div className="cards">
        {/* Sem link pelo mesmo motivo do cartão de qualificados: aqui contam-se
            registros de conversão por `converted_at`, e a listagem filtra leads
            por status — o total não se reproduz na tela de destino. */}
        <Card
          label="Conversões"
          value={data.conversions}
          hint="conversões registradas no período"
          tone={data.conversions > 0 ? 'ok' : undefined}
        />
        <Card
          label="Taxa de conversão"
          value={percent(data.conversion_rate)}
          // Numerador e denominador são coortes diferentes (conversão no
          // período ÷ leads criados no período): a conversão de um lead antigo
          // entra em cima de um denominador que não o inclui, e o valor pode
          // passar de 100%. Dizer isso aqui evita ler o número como erro.
          hint="conversões do período ÷ leads criados no período"
        />
        <Card
          label="Tempo até conversão"
          value={duration(data.avg_seconds_to_conversion)}
          hint="média entre criar o lead e converter"
        />
      </div>

      <h2 className="group-title">
        Operação <span className="muted">· agora</span>
      </h2>
      <div className="cards compact">
        <Card
          label="Aguardando atendimento"
          value={data.awaiting_support}
          hint={
            data.awaiting_support > 0
              ? 'conversas abertas sem operador — abrir fila'
              : 'nenhuma conversa na fila'
          }
          to="/conversations"
          tone={data.awaiting_support > 0 ? 'warn' : undefined}
        />
      </div>

      <Panel title="Usuários e conversões por dia">
        {series.isLoading && <Loading />}
        {series.isError && <ErrorBox error={series.error} />}
        {series.data && series.data.length === 0 && (
          <p className="muted">
            sem eventos no período — envie /start no bot para gerar dados
          </p>
        )}
        {series.data && series.data.length > 0 && (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={series.data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              {/* Preenchimento em degradê até transparente: a mesma série em
                  linha pura, sem área, é o traço mais "genérico" que um
                  gráfico de tendência pode ter — a área dá peso visual ao
                  volume, não só à direção. */}
              <defs>
                <linearGradient id="gradUsuarios" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chart.serie1} stopOpacity={0.32} />
                  <stop offset="100%" stopColor={chart.serie1} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradConversoes" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chart.serie2} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={chart.serie2} stopOpacity={0} />
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
                cursor={{ stroke: chart.grid }}
                labelFormatter={(valor) => `dia ${diaCurto(String(valor))}`}
              />
              <Legend
                verticalAlign="top"
                align="right"
                height={26}
                iconType="plainline"
                wrapperStyle={{ fontSize: 12, color: chart.axis }}
              />
              <Area
                type="monotone"
                dataKey="users"
                name="usuários"
                stroke={chart.serie1}
                strokeWidth={2.25}
                fill="url(#gradUsuarios)"
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Area
                type="monotone"
                dataKey="conversions"
                name="conversões"
                stroke={chart.serie2}
                strokeWidth={2.25}
                fill="url(#gradConversoes)"
                dot={false}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Panel>
    </>
  )
}
