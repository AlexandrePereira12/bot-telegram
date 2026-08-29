import type { ReactNode } from 'react'

export function Card({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  )
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

export function Loading() {
  return <p className="muted">carregando…</p>
}

export function ErrorBox({ error }: { error: unknown }) {
  return <p className="error">falha ao carregar: {(error as Error)?.message ?? 'erro'}</p>
}

export function Empty({ text = 'nenhum registro' }: { text?: string }) {
  return <p className="muted">{text}</p>
}

/** Métrica ausente é exibida como "—", nunca como zero: sem dado de
 *  investimento não inventamos CPL/CPA. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}

export function duration(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 24) return `${Math.floor(h / 24)}d ${h % 24}h`
  return h > 0 ? `${h}h ${m}min` : `${m}min`
}

export function datetime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('pt-BR')
}

const STATUS_CLASS: Record<string, string> = {
  CONVERTED: 'ok',
  QUALIFIED: 'ok',
  ACTIVE: 'ok',
  IN_SUPPORT: 'warn',
  QUALIFYING: 'warn',
  ASSIGNED: 'warn',
  OPEN: 'warn',
  LOST: 'danger',
  ARCHIVED: 'danger',
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${STATUS_CLASS[status] ?? ''}`}>{status}</span>
}
