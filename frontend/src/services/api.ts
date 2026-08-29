/**
 * Cliente da API.
 *
 * O access token fica em memória e no sessionStorage (não em localStorage):
 * some ao fechar a aba, reduzindo a janela de reuso de um token vazado.
 * O frontend nunca fala com o PostgreSQL — só com esta API.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const ACCESS_KEY = 'tb_access'
const REFRESH_KEY = 'tb_refresh'

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY)
}

// sessionStorage não notifica o React quando muda. Sem estes listeners, gravar
// o token depois do login não re-renderiza nada e a aplicação continua achando
// que ninguém está autenticado — o usuário loga e não sai do lugar.
const authListeners = new Set<() => void>()

export function subscribeAuth(listener: () => void): () => void {
  authListeners.add(listener)
  return () => {
    authListeners.delete(listener)
  }
}

function notifyAuthChange(): void {
  authListeners.forEach((listener) => listener())
}

export function setTokens(access: string, refresh: string): void {
  sessionStorage.setItem(ACCESS_KEY, access)
  sessionStorage.setItem(REFRESH_KEY, refresh)
  notifyAuthChange()
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  notifyAuthChange()
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function refreshTokens(): Promise<boolean> {
  const refresh = sessionStorage.getItem(REFRESH_KEY)
  if (!refresh) return false

  const response = await fetch(`${BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!response.ok) {
    clearTokens()
    return false
  }
  const data = await response.json()
  setTokens(data.access_token, data.refresh_token)
  return true
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const token = getAccessToken()
  const response = await fetch(`${BASE}/api/v1${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  // Access token curto: uma tentativa silenciosa de refresh antes de deslogar.
  if (response.status === 401 && retry && (await refreshTokens())) {
    return api<T>(path, options, false)
  }

  if (!response.ok) {
    let detail = `erro ${response.status}`
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export interface EnrollmentPayload {
  enrollment_required: true
  enrollment_token: string
  otpauth_uri: string
  secret: string
  expires_in: number
}

/** Conclui o cadastro do 2FA com o primeiro código do app autenticador. */
export async function confirm2FA(
  enrollmentToken: string,
  totpCode: string,
): Promise<void> {
  const response = await fetch(`${BASE}/api/v1/auth/2fa/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enrollment_token: enrollmentToken,
      totp_code: totpCode,
    }),
  })
  if (!response.ok) {
    let detail = 'código inválido — confira o número no app e tente de novo'
    if (response.status === 429) detail = 'muitas tentativas; aguarde um minuto'
    else if (response.status === 401) {
      try {
        const body = await response.json()
        if (String(body.detail).includes('expirado')) detail = String(body.detail)
      } catch {
        /* corpo não-JSON */
      }
    }
    throw new ApiError(response.status, detail)
  }
  const data = await response.json()
  setTokens(data.access_token, data.refresh_token)
}

/**
 * Login.
 *
 * Retorna `EnrollmentPayload` no primeiro acesso de um perfil que exige 2FA
 * (a sessão só é criada depois de confirmar o autenticador), ou `null`
 * quando os tokens já foram gravados.
 */
export async function login(
  email: string,
  password: string,
  totpCode?: string,
): Promise<EnrollmentPayload | null> {
  const response = await fetch(`${BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      totp_code: totpCode || null,
    }),
  })
  if (!response.ok) {
    // 422 é erro de formato do formulário, não de credencial. Mostrar
    // "credenciais inválidas" aqui manda o usuário conferir a senha quando o
    // problema é outro (ex.: colar o segredo 2FA no campo do código).
    if (response.status === 422) {
      let campo = ''
      try {
        const body = await response.json()
        const first = Array.isArray(body.detail) ? body.detail[0] : null
        const nome = first?.loc?.[first.loc.length - 1]
        campo =
          nome === 'totp_code'
            ? 'o código 2FA deve ter 6 dígitos (é o número que muda no app, não o segredo)'
            : nome === 'password'
              ? 'a senha precisa ter ao menos 8 caracteres'
              : nome === 'email'
                ? 'e-mail em formato inválido'
                : ''
      } catch {
        /* corpo não-JSON */
      }
      throw new ApiError(422, campo || 'dados do formulário inválidos')
    }
    const detail =
      response.status === 429
        ? 'muitas tentativas; aguarde um minuto'
        : 'credenciais inválidas'
    throw new ApiError(response.status, detail)
  }
  const data = await response.json()
  if (data.enrollment_required) return data as EnrollmentPayload
  setTokens(data.access_token, data.refresh_token)
  return null
}

/**
 * Envia imagem ou vídeo para usar nas mensagens do funil.
 *
 * Sem Content-Type manual: o browser precisa definir o boundary do
 * multipart, e informá-lo à mão quebra o parse no servidor.
 */
export async function uploadMedia(file: File): Promise<import('../types').MediaUpload> {
  const form = new FormData()
  form.append('file', file)

  const token = getAccessToken()
  const response = await fetch(`${BASE}/api/v1/content/media`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) {
    let detail = 'falha ao enviar o arquivo'
    if (response.status === 413) detail = 'arquivo grande demais'
    else {
      try {
        detail = (await response.json()).detail ?? detail
      } catch {
        /* corpo não-JSON */
      }
    }
    throw new ApiError(response.status, detail)
  }
  return response.json()
}
