import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode'

import { ThemeToggle } from '../components'
import { confirm2FA, login, type EnrollmentPayload } from '../services/api'

/** Só dígitos, no máximo 6 — impede colar aqui o segredo do autenticador. */
function onlyCode(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6)
}

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Presente = primeiro acesso: a tela vira o cadastro do autenticador.
  const [enrollment, setEnrollment] = useState<EnrollmentPayload | null>(null)
  const [showSecret, setShowSecret] = useState(false)

  const navigate = useNavigate()
  const queryClient = useQueryClient()

  async function finish() {
    await queryClient.invalidateQueries({ queryKey: ['me'] })
    navigate('/dashboard')
  }

  async function onLogin(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const pending = await login(email, password, totp)
      if (pending) {
        setEnrollment(pending)
        setTotp('')
      } else {
        await finish()
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function onConfirm(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await confirm2FA(enrollment!.enrollment_token, totp)
      await finish()
    } catch (err) {
      setError((err as Error).message)
      setTotp('')
    } finally {
      setBusy(false)
    }
  }

  if (enrollment) {
    return (
      <Enrollment
        data={enrollment}
        totp={totp}
        setTotp={setTotp}
        onSubmit={onConfirm}
        busy={busy}
        error={error}
        showSecret={showSecret}
        toggleSecret={() => setShowSecret((v) => !v)}
        cancel={() => {
          setEnrollment(null)
          setTotp('')
          setError(null)
        }}
      />
    )
  }

  return (
    <div className="login-wrap">
      <ThemeToggle />
      <form className="login-box" onSubmit={onLogin}>
        <p className="login-brand">Tráfego · Telegram</p>
        <h1>Entrar</h1>
        <p className="page-sub">Painel de tráfego e atendimento</p>

        <div className="field">
          <label htmlFor="email">E-mail</label>
          <input
            id="email"
            type="email"
            value={email}
            autoComplete="username"
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="password">Senha</label>
          <input
            id="password"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="totp">Código de 6 dígitos</label>
          <input
            id="totp"
            inputMode="numeric"
            value={totp}
            autoComplete="one-time-code"
            onChange={(e) => setTotp(onlyCode(e.target.value))}
            maxLength={6}
            placeholder="000000"
          />
          <small className="muted" style={{ fontSize: 11 }}>
            Só para quem já cadastrou o autenticador. No primeiro acesso, deixe
            em branco — a próxima tela mostra o QR.
          </small>
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? 'entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}

interface EnrollmentProps {
  data: EnrollmentPayload
  totp: string
  setTotp: (v: string) => void
  onSubmit: (e: React.FormEvent) => void
  busy: boolean
  error: string | null
  showSecret: boolean
  toggleSecret: () => void
  cancel: () => void
}

function Enrollment(props: EnrollmentProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // QR desenhado no próprio navegador a partir da otpauth_uri. Um endpoint
  // que devolvesse a imagem colocaria o segredo em URL — e daí em histórico,
  // log de proxy e header referer.
  useEffect(() => {
    if (!canvasRef.current) return
    QRCode.toCanvas(canvasRef.current, props.data.otpauth_uri, {
      width: 208,
      margin: 1,
      // Cores fixas pelo mesmo motivo da moldura branca abaixo.
      color: { dark: '#111111', light: '#ffffff' },
    }).catch(() => {
      /* falha no desenho: a chave manual abaixo continua servindo */
    })
  }, [props.data.otpauth_uri])

  return (
    <div className="login-wrap">
      <ThemeToggle />
      <form
        className="login-box"
        style={{ width: 380 }}
        onSubmit={props.onSubmit}
      >
        <p className="login-brand">Tráfego · Telegram</p>
        <h1>Configurar acesso</h1>
        <p className="page-sub">
          Seu perfil exige verificação em duas etapas. É rápido e só acontece
          uma vez.
        </p>

        <ol style={{ paddingLeft: 18, margin: '0 0 14px', lineHeight: 1.7 }}>
          <li>
            Abra o <strong>Google Authenticator</strong> (ou Authy) no celular
          </li>
          <li>
            Toque em <strong>+</strong> → <strong>Ler código QR</strong>
          </li>
          <li>Aponte para o código abaixo</li>
        </ol>

        <div
          // Branco fixo de propósito: o QR precisa de módulos escuros sobre
          // fundo claro para ser lido. Seguir o tema aqui derrubaria o
          // contraste que o leitor do celular espera.
          style={{
            background: '#fff',
            borderRadius: 10,
            padding: 12,
            display: 'grid',
            placeItems: 'center',
            marginBottom: 14,
          }}
        >
          <canvas ref={canvasRef} />
        </div>

        <button
          type="button"
          className="secondary"
          style={{ width: '100%', marginBottom: 14 }}
          onClick={props.toggleSecret}
        >
          {props.showSecret ? 'ocultar chave' : 'não consigo ler o QR'}
        </button>

        {props.showSecret && (
          <div
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 10,
              marginBottom: 14,
            }}
          >
            <small className="muted" style={{ fontSize: 11 }}>
              No app, escolha "inserir chave manualmente" e informe:
            </small>
            <code
              style={{
                display: 'block',
                marginTop: 6,
                wordBreak: 'break-all',
                fontSize: 12,
              }}
            >
              {props.data.secret}
            </code>
          </div>
        )}

        <div className="field">
          <label htmlFor="confirm">
            Digite o código de 6 dígitos que apareceu no app
          </label>
          <input
            id="confirm"
            inputMode="numeric"
            value={props.totp}
            autoComplete="one-time-code"
            onChange={(e) => props.setTotp(onlyCode(e.target.value))}
            maxLength={6}
            placeholder="000000"
            autoFocus
            required
          />
          <small className="muted" style={{ fontSize: 11 }}>
            O número muda a cada 30 segundos — se expirar, use o próximo.
          </small>
        </div>

        {props.error && <p className="error">{props.error}</p>}

        <button
          type="submit"
          disabled={props.busy || props.totp.length !== 6}
          style={{ width: '100%' }}
        >
          {props.busy ? 'confirmando…' : 'Confirmar e entrar'}
        </button>

        <button
          type="button"
          className="secondary"
          style={{ width: '100%', marginTop: 8 }}
          onClick={props.cancel}
        >
          Voltar
        </button>
      </form>
    </div>
  )
}
