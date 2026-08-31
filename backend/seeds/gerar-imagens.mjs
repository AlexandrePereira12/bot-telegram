/**
 * Gera as imagens fictícias do funil de teste (tema Aviator).
 *
 * Render em HTML/SVG pelo Chromium: nenhuma arte externa, nenhuma marca real
 * copiada — é material de teste, e precisa ser reproduzível por quem clonar o
 * repositório.
 */
import { chromium } from 'playwright'

const OUT = process.env.OUT ?? '/tmp'
const L = 1280
const A = 720

const base = (corpo, extra = '') => `
<html><head><meta charset="utf-8"><style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: ${L}px; height: ${A}px; overflow: hidden;
    font-family: 'DejaVu Sans', system-ui, sans-serif; color: #f3f5f7;
    background: radial-gradient(1100px 620px at 20% 12%, #1d2440 0%, #0d1018 62%, #07090e 100%);
    position: relative;
  }
  .grade {
    position: absolute; inset: 0; opacity: .28;
    background-image: linear-gradient(#ffffff12 1px, transparent 1px),
      linear-gradient(90deg, #ffffff12 1px, transparent 1px);
    background-size: 64px 64px;
  }
  .selo {
    position: absolute; right: 34px; top: 30px; display: flex; gap: 10px; align-items: center;
    font-size: 17px; letter-spacing: .16em; text-transform: uppercase; color: #8b95a8;
  }
  .selo b { color: #e71f4b; letter-spacing: .1em; }
  .rodape {
    position: absolute; left: 46px; right: 46px; bottom: 30px;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 16px; color: #7b8496; border-top: 1px solid #ffffff1a; padding-top: 16px;
  }
  .tag18 {
    border: 2px solid #e71f4b; color: #ff5c81; border-radius: 999px;
    padding: 4px 14px; font-weight: 700; font-size: 15px;
  }
  h1 { font-size: 58px; line-height: 1.05; letter-spacing: -.02em; }
  h2 { font-size: 30px; font-weight: 600; color: #aab3c4; margin-top: 14px; line-height: 1.35; }
  .conteudo { position: absolute; left: 46px; top: 104px; right: 46px; }
  ${extra}
</style></head><body><div class="grade"></div>
  <div class="selo"><span>demonstração</span><b>AVIATOR</b></div>
  ${corpo}
  <div class="rodape"><span>material fictício para teste do funil</span><span class="tag18">18+ · jogue com responsabilidade</span></div>
</body></html>`

/** Curva do voo, com o avião no fim e o multiplicador em destaque. */
const curva = (mult, cor) => `
<svg viewBox="0 0 1280 720" style="position:absolute;inset:0">
  <defs>
    <linearGradient id="g" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="${cor}" stop-opacity=".05"/>
      <stop offset="1" stop-color="${cor}" stop-opacity=".38"/>
    </linearGradient>
  </defs>
  <path d="M110 610 C 420 600, 700 520, 1010 250 L 1010 640 L 110 640 Z" fill="url(#g)"/>
  <path d="M110 610 C 420 600, 700 520, 1010 250" fill="none" stroke="${cor}" stroke-width="7" stroke-linecap="round"/>
  <g transform="translate(1010 250) rotate(-38)">
    <path d="M0 0 L-46 16 L-33 0 L-46 -16 Z" fill="#f3f5f7"/>
    <circle cx="6" cy="0" r="7" fill="${cor}"/>
  </g>
  <text x="110" y="230" fill="#f3f5f7" font-size="128" font-weight="700" font-family="DejaVu Sans">${mult}</text>
</svg>`

const telas = {
  'aviator-rodada': base(
    `${curva('2.41x', '#e71f4b')}
     <div style="position:absolute;left:110px;top:250px;font-size:26px;color:#aab3c4">
       multiplicador da rodada em andamento
     </div>`,
  ),
  'aviator-como-funciona': base(`
    <div class="conteudo">
      <h1>Como a rodada acontece</h1>
      <h2>O multiplicador sobe enquanto o avião voa — e a rodada termina<br>no momento em que ele vai embora.</h2>
      <div class="passos">
        <div class="passo"><span>1</span>Você entra na rodada antes da decolagem</div>
        <div class="passo"><span>2</span>O multiplicador começa em 1.00x e sobe</div>
        <div class="passo"><span>3</span>Se retirar antes do fim, vale o multiplicador do momento</div>
        <div class="passo"><span>4</span>Se não retirar a tempo, a rodada se encerra sem retirada</div>
      </div>
    </div>`,
    `.passos { margin-top: 34px; display: grid; gap: 12px; }
     .passo { display: flex; align-items: center; gap: 18px; font-size: 25px; color: #dfe4ec;
       background: #ffffff0a; border: 1px solid #ffffff14; border-radius: 16px; padding: 15px 22px; }
     .passo span { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center;
       background: #e71f4b; color: #fff; font-weight: 700; font-size: 22px; }`,
  ),
  'aviator-cash-out': base(
    `${curva('1.87x', '#22c07a')}
     <div style="position:absolute;right:60px;bottom:120px;text-align:right">
       <div style="font-size:24px;color:#aab3c4;margin-bottom:12px">retirada feita em</div>
       <div style="display:inline-block;background:#22c07a;color:#07130d;font-size:40px;font-weight:700;
         padding:18px 34px;border-radius:18px">RETIRAR · 1.87x</div>
     </div>`,
  ),
  'aviator-demo': base(`
    <div class="conteudo">
      <h1>Modo demonstração</h1>
      <h2>Saldo fictício, mesmas regras. Serve para entender a mecânica<br>antes de decidir qualquer coisa.</h2>
      <div class="cartoes">
        <div class="cartao"><b>R$ 0,00</b><span>valor real envolvido</span></div>
        <div class="cartao"><b>ilimitado</b><span>rodadas de teste</span></div>
        <div class="cartao"><b>igual</b><span>regras da rodada</span></div>
      </div>
    </div>`,
    `.cartoes { margin-top: 52px; display: flex; gap: 22px; }
     .cartao { flex: 1; background: #ffffff0a; border: 1px solid #ffffff14; border-radius: 20px; padding: 30px; }
     .cartao b { display: block; font-size: 44px; color: #6ea8ff; margin-bottom: 10px; }
     .cartao span { font-size: 22px; color: #aab3c4; }`,
  ),
  'aviator-pagamentos': base(`
    <div class="conteudo">
      <h1>Depósito e saque</h1>
      <h2>Pix como meio principal, com confirmação registrada nos dois sentidos.</h2>
      <div class="linha">
        <div class="etapa"><b>Pix</b><span>depósito identificado</span></div>
        <div class="seta">→</div>
        <div class="etapa"><b>saldo</b><span>disponível na conta</span></div>
        <div class="seta">→</div>
        <div class="etapa"><b>saque</b><span>na mesma titularidade</span></div>
      </div>
      <p class="obs">Conta e chave Pix precisam ser do mesmo CPF cadastrado.</p>
    </div>`,
    `.linha { margin-top: 56px; display: flex; align-items: center; gap: 18px; }
     .etapa { flex: 1; background: #ffffff0a; border: 1px solid #ffffff14; border-radius: 20px; padding: 28px; text-align: center; }
     .etapa b { display: block; font-size: 38px; margin-bottom: 8px; color: #f3f5f7; }
     .etapa span { font-size: 20px; color: #aab3c4; }
     .seta { font-size: 40px; color: #55607a; }
     .obs { margin-top: 34px; font-size: 22px; color: #8b95a8; }`,
  ),
  'aviator-limites': base(`
    <div class="conteudo">
      <h1>Limites e controle</h1>
      <h2>Ferramentas de contenção que existem antes de qualquer rodada.</h2>
      <div class="itens">
        <div class="item"><b>Limite diário</b><span>teto de valor por dia, definido por você</span></div>
        <div class="item"><b>Tempo de sessão</b><span>aviso e encerramento automático</span></div>
        <div class="item"><b>Autoexclusão</b><span>bloqueio temporário ou definitivo da conta</span></div>
      </div>
      <p class="alerta">Aposta é entretenimento pago, não fonte de renda. Só entra o valor que você pode perder.</p>
    </div>`,
    `.itens { margin-top: 34px; display: grid; gap: 12px; }
     .item { background: #ffffff0a; border-left: 5px solid #6ea8ff; border-radius: 14px; padding: 16px 24px; }
     .item b { font-size: 27px; }
     .item span { display: block; font-size: 21px; color: #aab3c4; margin-top: 6px; }
     .alerta { margin-top: 26px; font-size: 22px; color: #ffb454; }`,
  ),
  'aviator-atendimento': base(`
    <div class="conteudo">
      <h1>Falar com uma pessoa</h1>
      <h2>Conta, acesso, depósito ou saque: alguém do time assume a conversa<br>por aqui mesmo, neste chat.</h2>
      <div class="horario">
        <div><b>seg a sex</b><span>9h às 18h</span></div>
        <div><b>sábado</b><span>9h às 13h</span></div>
      </div>
    </div>`,
    `.horario { margin-top: 54px; display: flex; gap: 22px; }
     .horario div { background: #ffffff0a; border: 1px solid #ffffff14; border-radius: 20px; padding: 28px 42px; }
     .horario b { display: block; font-size: 34px; }
     .horario span { font-size: 24px; color: #aab3c4; }`,
  ),
}

const navegador = await chromium.launch({ executablePath: '/usr/bin/google-chrome-stable' })
const pagina = await navegador.newPage({ viewport: { width: L, height: A } })
for (const [nome, html] of Object.entries(telas)) {
  await pagina.setContent(html, { waitUntil: 'load' })
  const folga = await pagina.evaluate(() => {
    const c = document.querySelector('.conteudo')
    const r = document.querySelector('.rodape')
    if (!c) return null
    return Math.round(r.getBoundingClientRect().top - c.getBoundingClientRect().bottom)
  })
  await pagina.screenshot({ path: `${OUT}/${nome}.png` })
  console.log(`${nome}.png  folga até o rodapé: ${folga === null ? 'n/a' : folga + 'px'}`)
}
await navegador.close()
