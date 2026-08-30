import { useEffect, useRef, type ReactNode } from 'react'

import { toggleTheme, useTheme } from '../theme'

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
