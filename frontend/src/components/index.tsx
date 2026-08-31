import { useEffect, useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { toggleTheme, useTheme } from '../theme'

/** Indicador.
 *
 *  `hint` existe porque número solto não diz a que recorte pertence: no mesmo
 *  painel convivem métricas do período e métricas do momento, e sem a linha de
 *  contexto as duas parecem a mesma coisa. `to` transforma o cartão em atalho
 *  para a tela que detalha aquele número. */
export function Card({
  label,
  value,
  hint,
  to,
  tone,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  to?: string
  tone?: 'ok' | 'warn' | 'danger'
}) {
  const corpo = (
    <>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint !== undefined && <div className="card-hint">{hint}</div>}
    </>
  )
  const classe = `card${tone ? ` ${tone}` : ''}`

  if (to) {
    return (
      <Link className={`${classe} card-link`} to={to}>
        {corpo}
      </Link>
    )
  }
  return <div className={classe}>{corpo}</div>
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

/** `context` distingue leitura de escrita: "falha ao carregar" numa ação de
 *  salvar ou excluir descreve errado o que aconteceu. */
export function ErrorBox({
  error,
  context = 'falha ao carregar',
}: {
  error: unknown
  context?: string
}) {
  return (
    <p className="error">
      {context}: {(error as Error)?.message ?? 'erro'}
    </p>
  )
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
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`
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

/** `label` traduz o código sem mudar a cor, que continua vindo do valor cru.
 *  Sem a prop o badge segue exibindo o código — é o que as telas que não têm
 *  tradução esperam. */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <span className={`badge ${STATUS_CLASS[status] ?? ''}`}>{label ?? status}</span>
}

/** Alterna claro/escuro. A escolha fica no localStorage; sem escolha salva,
 *  vale a preferência do sistema (resolvida no index.html). */
export function ThemeToggle() {
  const theme = useTheme()
  const escuro = theme === 'dark'

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      title={escuro ? 'usar tema claro' : 'usar tema escuro'}
      aria-label={escuro ? 'usar tema claro' : 'usar tema escuro'}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true">
        {escuro ? (
          <path
            d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"
            fill="currentColor"
          />
        ) : (
          <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
          </g>
        )}
      </svg>
      <span className="toggle-label">{escuro ? 'escuro' : 'claro'}</span>
    </button>
  )
}


/** Modal sobre o <dialog> nativo.
 *
 *  Nativo em vez de div com overlay: foco preso dentro do diálogo, ESC e
 *  camada superior vêm prontos do navegador. O evento `close` (que o ESC
 *  dispara sem passar pelo React) precisa avisar o pai, senão o estado fica
 *  "aberto" enquanto a tela já fechou.
 */
export function Modal({
  open,
  title,
  onClose,
  children,
  width = 460,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  width?: number
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const fechar = useRef(onClose)
  fechar.current = onClose

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const aoFechar = () => fechar.current()
    dialog.addEventListener('close', aoFechar)
    return () => dialog.removeEventListener('close', aoFechar)
  }, [])

  return (
    <dialog ref={ref} className="modal" style={{ width }}>
      <header className="modal-head">
        <h2>{title}</h2>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="fechar"
        >
          ✕
        </button>
      </header>
      <div className="modal-body">{children}</div>
    </dialog>
  )
}

/** Confirmação de ação destrutiva.
 *
 *  Um `window.confirm` não cabe aqui: o texto precisa nomear quem será
 *  afetado e dizer o que a ação faz com o histórico — é essa diferença que
 *  o usuário precisa ler antes de decidir.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal open={open} title={title} onClose={onClose} width={420}>
      <div className="modal-text">{children}</div>
      <div className="modal-actions">
        <button type="button" className="secondary" onClick={onClose} disabled={busy}>
          Cancelar
        </button>
        <button
          type="button"
          className={danger ? 'danger' : ''}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? 'aplicando…' : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

/** Iniciais para o bloco de identidade. Nome quando existe; senão, o e-mail. */
export function initials(name: string | null, email: string): string {
  const base = (name ?? email.split('@')[0]).trim()
  const partes = base.split(/[\s._-]+/).filter(Boolean)
  const letras = partes.length > 1 ? partes[0][0] + partes[1][0] : base.slice(0, 2)
  return letras.toUpperCase()
}

/** Seletor de janela de análise.
 *
 *  O mesmo controle no Dashboard, no Funil e no Analytics: trocar o período
 *  em uma tela e não achar o controle na outra é o que fazia o número parecer
 *  incoerente entre elas. */
export function PeriodPicker({
  days,
  onChange,
  options = [7, 30, 90],
}: {
  days: number
  onChange: (days: number) => void
  options?: number[]
}) {
  return (
    <div className="period-picker" role="group" aria-label="período">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={option === days ? '' : 'secondary'}
          aria-pressed={option === days}
          onClick={() => onChange(option)}
        >
          {option} dias
        </button>
      ))}
    </div>
  )
}

/** Paginação por offset.
 *
 *  A API devolve lista sem total, então a existência de próxima página é
 *  inferida da página cheia. Sem isto a tela trava nos primeiros 100 registros
 *  sem nada indicando que existe mais coisa. */
export function Pager({
  page,
  pageSize,
  count,
  onChange,
}: {
  page: number
  pageSize: number
  count: number
  onChange: (page: number) => void
}) {
  const primeiro = page * pageSize + 1
  const ultimo = page * pageSize + count
  const temProxima = count === pageSize

  if (page === 0 && !temProxima) {
    return <p className="pager-info">{count === 0 ? 'nenhum registro' : `${count} registro${count > 1 ? 's' : ''}`}</p>
  }

  return (
    <div className="pager">
      <span className="pager-info">
        {count === 0 ? 'nenhum registro nesta página' : `${primeiro}–${ultimo}`}
      </span>
      <button
        type="button"
        className="secondary"
        disabled={page === 0}
        onClick={() => onChange(page - 1)}
      >
        ← anterior
      </button>
      <button
        type="button"
        className="secondary"
        disabled={!temProxima}
        onClick={() => onChange(page + 1)}
      >
        próxima →
      </button>
    </div>
  )
}

/** Resumo dos filtros aplicados, cada um removível.
 *
 *  Filtro que só existe dentro de um `select` some da vista quando a lista é
 *  rolada; a lista vazia então parece defeito, e não recorte. */
export function FilterChips({
  chips,
  onClear,
}: {
  chips: { key: string; label: string; onRemove: () => void }[]
  onClear: () => void
}) {
  if (chips.length === 0) return null

  return (
    <div className="chips">
      <span className="muted">filtros:</span>
      {chips.map((chip) => (
        <span className="chip" key={chip.key}>
          {chip.label}
          <button
            type="button"
            className="chip-remove"
            onClick={chip.onRemove}
            aria-label={`remover filtro ${chip.label}`}
          >
            ✕
          </button>
        </span>
      ))}
      <button type="button" className="link" onClick={onClear}>
        limpar tudo
      </button>
    </div>
  )
}
