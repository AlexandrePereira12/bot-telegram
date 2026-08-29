/**
 * Fluxo de autenticacao no browser real.
 *
 * Existe porque teste de API nao cobre este caminho: o login ja respondia 200
 * enquanto a tela nao saia do lugar, porque o token era lido uma vez no render
 * em vez de assinado. So um browser de verdade pega esse tipo de regressao.
 *
 * Pre-requisitos: stack no ar e 2FA do operador reiniciado
 *   docker compose exec api python -m app.cli reset-2fa --email <email>
 *
 * Uso: node e2e/auth-flow.mjs [--base http://localhost:8080] [--headed]
 */
import { chromium } from 'playwright'
import { execSync } from 'node:child_process'

const arg = (nome, padrao) => {
  const i = process.argv.indexOf(`--${nome}`)
  return i > -1 ? process.argv[i + 1] : padrao
}

const BASE = arg('base', process.env.E2E_BASE ?? 'http://localhost:8080')
const EMAIL = arg('email', process.env.E2E_EMAIL ?? 'admin@empresa.com')
const SENHA = arg('senha', process.env.E2E_SENHA ?? '')
const PROJETO = arg('projeto', process.env.E2E_PROJECT ?? '')

if (!SENHA) {
  console.error('informe a senha: --senha <valor> ou E2E_SENHA')
  process.exit(2)
}

// O codigo TOTP e calculado pelo container da API, que ja tem pyotp.
const totpFor = (secret) => {
  const p = PROJETO ? `-p ${PROJETO} ` : ''
  return execSync(
    `docker compose ${p}exec -T api python -c "import pyotp;print(pyotp.TOTP('${secret}').now())"`,
    { cwd: new URL('..', import.meta.url).pathname + '..' },
  ).toString().trim()
}

// CHROME_PATH cobre o caso de os browsers do Playwright nao estarem baixados
// nesta maquina (ou estarem numa versao diferente da que o pacote espera).
const browser = await chromium.launch({
  headless: !process.argv.includes('--headed'),
  ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
})
const page = await browser.newPage()
const erros = []
page.on('console', (m) => m.type() === 'error' && erros.push(m.text()))
page.on('pageerror', (e) => erros.push(String(e)))

// Captura o segredo direto da resposta do login (é o que o QR codifica).
let secret = null
page.on('response', async (r) => {
  if (r.url().includes('/auth/login') && r.status() === 200) {
    try {
      const b = await r.json()
      if (b.secret) secret = b.secret
    } catch {}
  }
})

console.log('1. abrindo o dashboard')
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })

console.log('2. preenchendo e-mail e senha (sem codigo)')
await page.fill('#email', EMAIL)
await page.fill('#password', SENHA)
await page.click('button[type=submit]')

console.log('3. esperando a tela de configuracao do 2FA')
await page.waitForSelector('text=Configurar acesso', { timeout: 10000 })

const temQR = await page.locator('canvas').isVisible()
const qrBox = await page.locator('canvas').boundingBox()
console.log(`   QR renderizado: ${temQR} (${qrBox?.width}x${qrBox?.height}px)`)
if (!secret) throw new Error('segredo nao veio na resposta do login')

console.log('4. lendo o codigo do autenticador e confirmando')
await page.fill('#confirm', totpFor(secret))
await page.click('button[type=submit]')

console.log('5. esperando o dashboard carregar')
await page.waitForURL('**/dashboard', { timeout: 15000 })
await page.waitForSelector('h1:has-text("Dashboard")', { timeout: 15000 })

const url = page.url()
const cards = await page.locator('.card .label').allTextContents()
console.log(`   URL: ${url}`)
console.log(`   indicadores: ${cards.join(', ')}`)

console.log('6. navegando pelas paginas')
for (const [rota, titulo] of [
  ['/leads', 'Leads'],
  ['/campaigns', 'Campanhas'],
  ['/funnel', 'Funil'],
  ['/conversations', 'Conversas'],
  ['/content', 'Conteúdo do bot'],
  ['/analytics', 'Analytics'],
]) {
  await page.click(`a[href="${rota}"]`)
  await page.waitForSelector(`h1:has-text("${titulo}")`, { timeout: 10000 })
  console.log(`   ${rota} -> ok`)
}

console.log('7. recarregando (sessao deve persistir)')
await page.reload({ waitUntil: 'networkidle' })
await page.waitForSelector('h1', { timeout: 10000 })
console.log(`   apos reload: ${page.url()}`)

console.log('8. logout')
await page.click('button:has-text("Sair")')
await page.waitForSelector('h1:has-text("Entrar")', { timeout: 10000 })
console.log(`   voltou para: ${page.url()}`)

await page.screenshot({ path: 'e2e/final.png' })
await browser.close()

if (erros.length) {
  console.log('\nERROS NO CONSOLE:')
  erros.forEach((e) => console.log('  ' + e))
  process.exit(1)
}
console.log('\nE2E BROWSER OK — sem erros de console')
