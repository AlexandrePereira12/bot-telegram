import { useEffect, useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { toggleTheme, useTheme } from '../theme'

const ICON_PATHS = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </>
  ),
  campaigns: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  content: (
    <>
      <rect x="3" y="4" width="18" height="13" rx="2.5" />
      <path d="M7.5 9h9M7.5 12.5h6" />
    </>
  ),
  funnel: <path d="M3 4h18l-6.5 8.5V19l-5 2v-8.5z" />,
  leads: (
    <>
      <circle cx="8.5" cy="8" r="3" />
      <path d="M2.5 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <circle cx="17" cy="8.5" r="2.6" />
      <path d="M14.2 14.4c2.6.4 4.6 2.5 4.8 5.6" />
    </>
  ),
  conversations: (
    <path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
  ),
  analytics: (
    <>
      <rect x="3.5" y="12" width="3.2" height="8.5" rx="0.8" />
      <rect x="10.4" y="7" width="3.2" height="13.5" rx="0.8" />
      <rect x="17.3" y="3" width="3.2" height="17.5" rx="0.8" />
    </>
  ),
  operators: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="2.2" />
      <circle cx="8.5" cy="12" r="2.2" />
      <path d="M13.2 10h5.3M13.2 14h3.6" />
    </>
  ),
  logout: (
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </>
  ),
  inbox: (
    <>
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </>
  ),
  alert: (
    <>
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </>
  ),
  /* Clipe e microfone seguem a silhueta que todo aplicativo de mensagem usa —
     aqui a familiaridade vale mais que originalidade: quem abre o chat precisa
     reconhecer "anexar" e "gravar" sem ler nada. */
  paperclip: (
    <path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
  ),
  mic: (
    <>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </>
  ),
  send: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />,
  trash: (
    <>
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
    </>
  ),
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 8.6a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </>
  ),
  menu: (
    <>
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </>
  ),
  chevronLeft: <path d="M15 18l-6-6 6-6" />,
  spinner: (
    <>
      <circle cx="12" cy="12" r="9" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </>
  ),
} as const

export type IconName = keyof typeof ICON_PATHS

/** Ícones da interface — traço simples, sem biblioteca externa.
 *
 *  Mesmo padrão do SVG do `ThemeToggle` (que já existia antes desta tela):
 *  stroke/currentColor, 24x24, cantos arredondados. Um conjunto coerente de
 *  ícones no lugar de texto puro na navegação é o que mais rápido tira a
 *  cara de rascunho de uma tela — mas continua sendo decoração; nenhum ícone
 *  aqui é o único portador de informação (`aria-hidden`, o texto ao lado
 *  continua fazendo o trabalho para leitor de tela). */
export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name]}
    </svg>
  )
}

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
  return (
    <p className="state">
      <Icon name="spinner" className="state-spinner" />
      carregando…
    </p>
  )
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
    <p className="state state-error">
      <Icon name="alert" />
      {context}: {(error as Error)?.message ?? 'erro'}
    </p>
  )
}

export function Empty({ text = 'nenhum registro' }: { text?: string }) {
  return (
    <p className="state">
      <Icon name="inbox" />
      {text}
    </p>
  )
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
