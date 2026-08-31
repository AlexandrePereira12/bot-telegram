/**
 * Validação do painel analítico (Dashboard, Funil, Leads e detalhe do lead)
 * contra a API real, em browser.
 *
 * Cobre o que teste de API não pega: número do cartão contra o endpoint que o
 * alimenta, funil com dado não monotônico, filtros na URL, paginação, fuso do
 * filtro de data e o gate de campanha por perfil.
 *
 * Pré-requisitos: stack no ar, frontend servido em 5173 e dois operadores sem
 * 2FA (ANALYST e OPERATOR — perfis com 2FA exigiriam o enrollment do QR):
 *
 *   docker compose exec api python -m app.cli create-admin \
 *     --email qa.analyst@empresa.com --role ANALYST
 *   VITE_API_BASE_URL=http://localhost:8080 npm run dev
 *
 * Uso:
 *   QA_ANALYST_PWD=... QA_OPERATOR_PWD=... node e2e/painel-analitico.mjs
 */
import { chromium } from 'playwright'

const APP = 'http://localhost:5173'
const API = 'http://localhost:8080/api/v1'
const ANALYST = { email: 'qa.analyst@empresa.com', senha: process.env.QA_ANALYST_PWD }
const OPERADOR = { email: 'qa.operator@empresa.com', senha: process.env.QA_OPERATOR_PWD }

const resultados = []
const check = (nome, ok, detalhe = '') => {
  resultados.push({ nome, ok, detalhe })
  console.log(`${ok ? 'PASS ' : 'FALHA'} — ${nome}${detalhe ? ` :: ${detalhe}` : ''}`)
}

async function token(cred) {
  const r = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: cred.email, password: cred.senha, totp_code: null }),
  })
  if (!r.ok) throw new Error(`login API ${r.status}`)
  return (await r.json()).access_token
}

async function apiGet(caminho, jwt) {
  const r = await fetch(`${API}${caminho}`, { headers: { Authorization: `Bearer ${jwt}` } })
  if (!r.ok) throw new Error(`${caminho} -> ${r.status}`)
  return r.json()
}

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH })

function instrumentar(page, problemas, requisicoes) {
  // O 404 de /favicon.ico é do servidor de desenvolvimento (o nginx da stack
  // serve o ícone normalmente) e não diz nada sobre as telas.
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    if (/favicon/.test(m.text())) return
    problemas.push(`console: ${m.text()}`)
  })
  page.on('pageerror', (e) => problemas.push(`pageerror: ${e}`))
  page.on('response', (r) => {
    if (r.status() >= 400 && !r.url().endsWith('/favicon.ico'))
      problemas.push('http ' + r.status() + ' ' + r.url() + ' @ ' + page.url())
    if (!r.url().includes('/api/v1')) return
    requisicoes.push(`${r.status()} ${r.url().replace(API, '')}`)
  })
}

async function sessao(cred) {
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } })
  const page = await context.newPage()
  // O servidor de desenvolvimento não serve /favicon.ico (o nginx da stack
  // serve). Atender aqui prova que o único 404 do console era esse.
  await page.route("**/favicon.ico", (rota) => rota.fulfill({ status: 200, body: "" }))
  const problemas = []
  const requisicoes = []
  instrumentar(page, problemas, requisicoes)

  await page.goto(`${APP}/login`, { waitUntil: 'networkidle' })
  await page.fill('input[type=email]', cred.email)
  await page.fill('input[type=password]', cred.senha)
  await page.click('button[type=submit]')
  await page.waitForURL(/\/(dashboard|leads)/, { timeout: 15000 })
  return { context, page, problemas, requisicoes }
}

// ---------------------------------------------------------------- ANALYST
const jwt = await token(ANALYST)
const { context, page, problemas, requisicoes } = await sessao(ANALYST)
check('login ANALYST leva ao painel', /\/(dashboard|leads)/.test(page.url()), page.url())

const overview30 = await apiGet('/analytics/overview?days=30', jwt)
await page.goto(`${APP}/dashboard`, { waitUntil: 'networkidle' })
await page.waitForTimeout(400)

const valorDoCartao = async (rotulo) =>
  page.$eval(`.card:has(.label:text-is("${rotulo}")) .value`, (el) => el.textContent.trim())

check(
  'Dashboard · Usuários bate com /analytics/overview',
  (await valorDoCartao('Usuários')) === String(overview30.users),
  `tela=${await valorDoCartao('Usuários')} api=${overview30.users}`,
)
check(
  'Dashboard · Leads bate com a API',
  (await valorDoCartao('Leads')) === String(overview30.leads),
  `tela=${await valorDoCartao('Leads')} api=${overview30.leads}`,
)
check(
  'Dashboard · Conversões e taxa batem com a API',
  (await valorDoCartao('Conversões')) === String(overview30.conversions) &&
    (await valorDoCartao('Taxa de conversão')) ===
      `${(overview30.conversion_rate * 100).toFixed(1)}%`,
  `conv=${await valorDoCartao('Conversões')}/${overview30.conversions} taxa=${await valorDoCartao('Taxa de conversão')}/${overview30.conversion_rate}`,
)
check(
  'Dashboard · Aguardando atendimento bate com a API',
  (await valorDoCartao('Aguardando atendimento')) === String(overview30.awaiting_support),
)

const overview7 = await apiGet('/analytics/overview?days=7', jwt)
await page.click('.period-picker button:text-is("7 dias")')
await page.waitForTimeout(900)
check(
  'Dashboard · seletor de 7 dias recarrega os números',
  (await valorDoCartao('Usuários')) === String(overview7.users) &&
    overview7.users !== overview30.users,
  `7d tela=${await valorDoCartao('Usuários')} api=${overview7.users} / 30d=${overview30.users}`,
)
const grupoOperacao = await page.$eval('.group-title:has-text("Operação")', (el) =>
  el.textContent.replace(/\s+/g, ' ').trim(),
)
check('Dashboard · grupo de operação rotulado "agora"', /agora/.test(grupoOperacao), grupoOperacao)
check(
  'Dashboard · cartões de qualificados e conversões não são links',
  (await page.$('.card-link:has(.label:text-is("Qualificados"))')) === null &&
    (await page.$('.card-link:has(.label:text-is("Conversões"))')) === null,
)

await page.click('.period-picker button:text-is("30 dias")')
await page.waitForTimeout(700)
await page.click('.card-link:has(.label:text-is("Leads"))')
await page.waitForURL(/\/leads\?from=/, { timeout: 8000 })
await page.waitForTimeout(800)
const desde = new URL(page.url()).searchParams.get('from')
const inicioLocal = new Date(`${desde}T00:00:00`).toISOString()
const listaPeriodo = await apiGet(
  `/leads?created_from=${encodeURIComponent(inicioLocal)}&limit=500`,
  jwt,
)
check(
  'Cartão Leads abre a lista do mesmo período (fronteira do dia local)',
  listaPeriodo.length >= overview30.leads &&
    listaPeriodo.length - overview30.leads <= Math.ceil(overview30.leads * 0.05),
  `lista=${listaPeriodo.length} cartão=${overview30.leads} from=${desde}`,
)

// --- Funil
const funilApi = await apiGet('/analytics/funnel?days=30', jwt)
await page.goto(`${APP}/funnel`, { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
const etapas = await page.$$eval('.funnel-step', (nós) =>
  nós.map((n) => ({
    nome: n.querySelector('.funnel-name strong').textContent.trim(),
    contagem: n.querySelector('.funnel-count').textContent.trim(),
    largura: Number.parseFloat(n.querySelector('.funnel-bar').style.width),
    delta: n.querySelector('.funnel-delta').textContent.replace(/\s+/g, ' ').trim(),
    gargalo: n.classList.contains('gargalo'),
  })),
)
check(
  'Funil · uma linha por etapa da API, com as mesmas contagens',
  etapas.length === funilApi.length &&
    etapas.every((e, i) => e.contagem === String(funilApi[i].count)),
  etapas.map((e) => `${e.nome}=${e.contagem}`).join(' '),
)
check(
  'Funil · nenhuma barra passa de 100% da régua',
  etapas.every((e) => e.largura <= 100),
  etapas.map((e) => `${e.nome}:${e.largura.toFixed(1)}%`).join(' '),
)
const etapaAcima = etapas.find((e) => /acima da anterior/.test(e.delta))
const indiceApiAcima = funilApi.findIndex(
  (passo, i) => i > 0 && passo.count > funilApi[i - 1].count,
)
check(
  'Funil · etapa que supera a anterior é marcada como tal (dado não monotônico)',
  Boolean(etapaAcima) &&
    etapas.findIndex((e) => /acima da anterior/.test(e.delta)) === indiceApiAcima &&
    !etapas.some((e) => /−\s*-/.test(e.delta)),
  etapaAcima ? `${etapaAcima.nome}: ${etapaAcima.delta}` : 'nenhuma etapa marcada',
)
let piorQueda = { i: -1, valor: -1 }
funilApi.forEach((passo, i) => {
  if (i === 0) return
  const anterior = funilApi[i - 1].count
  if (!anterior || passo.count >= anterior) return
  const queda = 1 - passo.count / anterior
  if (queda > piorQueda.valor) piorQueda = { i, valor: queda }
})
check(
  'Funil · destaque cai na etapa de maior queda proporcional',
  etapas.findIndex((e) => e.gargalo) === piorQueda.i,
  `tela=${etapas.findIndex((e) => e.gargalo)} esperado=${piorQueda.i} (${etapas[piorQueda.i]?.nome})`,
)
const estadosApi = await apiGet('/analytics/states', jwt)
const totalEstados = Object.values(estadosApi).reduce((a, b) => a + b, 0)
const totalTela = await page.$eval(
  '.panel:has-text("estado atual") tbody tr:last-child td:nth-child(2)',
  (el) => el.textContent.trim(),
)
check(
  'Funil · total de usuários por estado bate com a API',
  totalTela === String(totalEstados),
  `tela=${totalTela} api=${totalEstados}`,
)
const funil7 = await apiGet('/analytics/funnel?days=7', jwt)
await page.click('.period-picker button:text-is("7 dias")')
await page.waitForTimeout(900)
const entradas7 = await page.$eval('.funnel-step:first-child .funnel-count', (el) =>
  el.textContent.trim(),
)
check(
  'Funil · seletor de período recarrega as etapas',
  entradas7 === String(funil7[0].count) && funil7[0].count !== funilApi[0].count,
  `7d tela=${entradas7} api=${funil7[0].count} / 30d=${funilApi[0].count}`,
)

// --- Leads: deep link, filtros, chips, paginação
await page.goto(`${APP}/leads?campaign=1`, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
const campanhaSelecionada = await page.$eval('#filtro-campanha', (el) => el.value)
const filtradoCampanha = await apiGet('/leads?campaign_id=1&limit=500', jwt)
const linhasCampanha = await page.$$eval('tbody tr', (nós) => nós.length)
check(
  'Leads · deep link de campanha preenche o controle e filtra a lista',
  campanhaSelecionada === '1' &&
    linhasCampanha === Math.min(filtradoCampanha.length, 50) &&
    filtradoCampanha.length > 0,
  `select=${campanhaSelecionada} tela=${linhasCampanha} api=${filtradoCampanha.length}`,
)
const nomesCampanha = await page.$$eval('tbody tr td:nth-child(4)', (nós) =>
  [...new Set(nós.map((n) => n.textContent.trim()))],
)
check(
  'Leads · coluna de campanha mostra o nome, não o id',
  nomesCampanha.every((v) => v === 'Campanha de teste'),
  nomesCampanha.join(' | '),
)

await page.goto(`${APP}/leads?status=CONVERTED&campaign=1`, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
const chips = await page.$$eval('.chip', (nós) => nós.map((n) => n.textContent.trim()))
check('Leads · filtros ativos aparecem como chips', chips.length === 2, chips.join(' | '))
const antesDoChip = await page.$$eval('tbody tr', (nós) => nós.length)
await page.click('.chip:has-text("status") .chip-remove')
await page.waitForTimeout(800)
const depoisDoChip = await page.$$eval('tbody tr', (nós) => nós.length)
check(
  'Leads · remover chip tira o filtro da URL e amplia a lista',
  !new URL(page.url()).searchParams.has('status') && depoisDoChip > antesDoChip,
  `${antesDoChip} -> ${depoisDoChip} linhas; url=${new URL(page.url()).search}`,
)

await page.goto(`${APP}/leads`, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
const idsPagina1 = await page.$$eval('tbody tr td:first-child', (nós) =>
  nós.map((n) => n.textContent.trim()),
)
await page.click('.pager button:has-text("próxima")')
await page.waitForTimeout(900)
const idsPagina2 = await page.$$eval('tbody tr td:first-child', (nós) =>
  nós.map((n) => n.textContent.trim()),
)
check(
  'Leads · página 2 traz registros diferentes',
  idsPagina1.length === 50 &&
    idsPagina2.length > 0 &&
    idsPagina1.every((id) => !idsPagina2.includes(id)),
  `p1=${idsPagina1.length} p2=${idsPagina2.length} url=${new URL(page.url()).search}`,
)
await page.click('.pager button:has-text("anterior")')
await page.waitForTimeout(900)
const voltouPagina1 = await page.$$eval('tbody tr td:first-child', (nós) =>
  nós.map((n) => n.textContent.trim()),
)
check(
  'Leads · botão anterior volta para a mesma primeira página',
  JSON.stringify(voltouPagina1) === JSON.stringify(idsPagina1),
)
await page.goto(`${APP}/leads?page=1`, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
await page.selectOption('#filtro-status', 'CONVERTED')
await page.waitForTimeout(900)
check(
  'Leads · trocar filtro volta para a primeira página',
  !new URL(page.url()).searchParams.has('page'),
  page.url(),
)

// --- Fuso horário: lead criado às 22:00 (01:00 UTC do dia seguinte)
const leads500 = await apiGet('/leads?limit=500', jwt)
const leadFuso = leads500.find((l) => l.id === 133) ?? leads500.find((l) => l.source === 'meta')
const diaLocalDoLead = new Date(leadFuso.created_at).toLocaleDateString('en-CA')
await page.goto(`${APP}/leads?to=${diaLocalDoLead}`, { waitUntil: 'networkidle' })
await page.waitForTimeout(900)
const idsAte = await page.$$eval('tbody tr td:first-child', (nós) =>
  nós.map((n) => n.textContent.trim()),
)
check(
  'Leads · "criado até <dia>" inclui lead das 22:00 daquele dia (fuso local)',
  idsAte.includes(`#${leadFuso.id}`),
  `lead=#${leadFuso.id} criado=${leadFuso.created_at} (dia local ${diaLocalDoLead}) primeiros=${idsAte.slice(0, 3)}`,
)

// --- Detalhe do lead aberto por link direto (aba nova, sessão própria)
const abaNova = await context.newPage()
await abaNova.route("**/favicon.ico", (rota) => rota.fulfill({ status: 200, body: "" }))
const problemasAba = []
const requisicoesAba = []
instrumentar(abaNova, problemasAba, requisicoesAba)
await abaNova.addInitScript((t) => sessionStorage.setItem('tb_access', t), jwt)
await abaNova.goto(`${APP}/leads/${leadFuso.id}`, { waitUntil: 'networkidle' })
await abaNova.waitForTimeout(900)
const tituloDetalhe = await abaNova.$eval('h1', (el) => el.textContent.trim())
const textoDetalhe = await abaNova.$eval('main.content', (el) => el.innerText)
check(
  'Detalhe do lead traduz status, estado do funil e consentimento',
  /Em qualificação|Qualificado|Convertido|Novo|Perdido|Em atendimento/.test(textoDetalhe) &&
    /Qualificação|Boas-vindas|Informação|Atendimento humano|Consentimento/.test(textoDetalhe) &&
    /Aceito|Pendente|Recusado|Revogado/.test(textoDetalhe),
  tituloDetalhe,
)
await abaNova.click('button.link:has-text("voltar")')
await abaNova.waitForTimeout(700)
check(
  'Detalhe aberto por link direto volta para a listagem sem sair do app',
  abaNova.url().endsWith('/leads'),
  `${tituloDetalhe} -> ${abaNova.url()}`,
)
check(
  'Detalhe do lead · sem falha de console ou HTTP',
  problemasAba.length === 0,
  problemasAba.slice(0, 3).join(' | '),
)
await abaNova.close()

check(
  'ANALYST · nenhuma falha de console ou HTTP nas telas',
  problemas.length === 0,
  problemas.slice(0, 4).join(' | '),
)

// --- Tema escuro pelo próprio botão (recolore gráfico e painéis)
await page.goto(`${APP}/dashboard`, { waitUntil: 'networkidle' })
await page.click('.theme-toggle')
await page.waitForTimeout(700)
const tema = await page.evaluate(() => document.documentElement.dataset.theme)
const corDaLinha = await page.$eval('.recharts-line path', (el) => el.getAttribute('stroke'))
check(
  'Dashboard · alternar tema recolore também o gráfico',
  tema === 'dark' && corDaLinha.toLowerCase() === '#63b3c2',
  `tema=${tema} linha=${corDaLinha}`,
)
await page.click('.theme-toggle')
await context.close()

// ---------------------------------------------------------------- OPERADOR
const sessaoOperador = await sessao(OPERADOR)
await sessaoOperador.page.goto(`${APP}/leads`, { waitUntil: 'networkidle' })
await sessaoOperador.page.waitForTimeout(900)
const temFiltroCampanha = await sessaoOperador.page.$('#filtro-campanha')
const chamouCampanhas = sessaoOperador.requisicoes.filter((r) => r.includes('/campaigns'))
check('OPERADOR · filtro de campanha não aparece', temFiltroCampanha === null)
check(
  'OPERADOR · nenhuma requisição a /campaigns',
  chamouCampanhas.length === 0,
  chamouCampanhas.join(' | '),
)
const celulaCampanha = await sessaoOperador.page.$$eval('tbody tr td:nth-child(4)', (nós) =>
  nós.slice(0, 5).map((n) => n.textContent.trim()),
)
check(
  'OPERADOR · coluna de campanha cai para o #id',
  celulaCampanha.length > 0 && celulaCampanha.every((v) => /^#\d+$|^—$/.test(v)),
  celulaCampanha.join(' | '),
)
const menu = await sessaoOperador.page.$$eval('.nav-link', (nós) =>
  nós.map((n) => n.textContent.trim()),
)
check(
  'OPERADOR · menu não oferece Dashboard, Funil nem Analytics',
  !menu.includes('Dashboard') && !menu.includes('Funil') && !menu.includes('Analytics'),
  menu.join(' | '),
)
check(
  'OPERADOR · nenhuma falha de console ou HTTP',
  sessaoOperador.problemas.length === 0,
  sessaoOperador.problemas.slice(0, 4).join(' | '),
)
await sessaoOperador.context.close()

await browser.close()

const falhas = resultados.filter((r) => !r.ok)
console.log(`\n${resultados.length - falhas.length}/${resultados.length} verificações passaram`)
process.exit(falhas.length ? 1 : 0)
