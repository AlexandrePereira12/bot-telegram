# Dashboard (frontend)

React + Vite + TanStack Query. Servido por nginx como SPA; toda a comunicação
é com a API em `/api/v1`.

## Aparência

### Tema claro e escuro

O tema vive no atributo `data-theme` do `<html>`, não no estado do React.

- `index.html` tem um script inline que lê `localStorage.theme` e carimba o
  atributo **antes** do bundle carregar. Sem isso, toda carga piscaria no tema
  errado até o React montar.
- `src/theme.ts` só mantém o atributo em sincronia com o `localStorage` e
  notifica quem assina (`useTheme`). Primeira visita, sem preferência salva:
  vale o `prefers-color-scheme` do sistema.
- O botão de troca (`ThemeToggle`) está na barra lateral e na tela de login.

O claro é o tema base (`:root`) e o escuro é a variação (`[data-theme='dark']`).
Cada tema define `color-scheme` — sem isso, `select`, barras de rolagem e o
preenchimento automático do navegador renderizam no esquema errado.

As cores semânticas (`--ok`, `--warn`, `--danger`) têm valores **diferentes**
por tema: o mesmo verde legível sobre fundo quase preto some sobre papel.

### Separação visual por tema

Painéis e cards usam um mecanismo de separação por tema, nunca os dois
empilhados:

- claro: fundo quase igual ao da página, quem separa é a borda (`--panel-border`);
- escuro: o degrau de fundo já separa, então a borda fica transparente.

### Tipografia

IBM Plex Sans no texto e IBM Plex Mono nos números (valores dos cards, colunas
`.num`, IDs). Empacotadas via `@fontsource`, subset latino apenas:

- o painel roda em rede de cliente e não pode depender de CDN externa — sem
  rede para o Google Fonts, a interface cairia na fonte de sistema;
- servir do próprio domínio também evita expor o IP de quem acessa a terceiros;
- os subsets cirílico/grego/vietnamita triplicariam os arquivos sem uso.

### Gráficos (Recharts)

`stroke` e `fill` são atributos de apresentação do SVG e **não** aceitam
`var(--token)`. Por isso `useChartTokens()` lê os tokens do `getComputedStyle`
e depende do tema atual: sem essa dependência, o valor seria lido uma vez e o
gráfico ficaria com as cores do tema anterior após a troca.

O QR code do cadastro de 2FA é a exceção deliberada — módulos escuros sobre
moldura branca fixa, independente do tema, porque é o contraste que o leitor
do celular espera.

### Sistema de ícones

`Icon` (`components/index.tsx`) é um conjunto próprio de ícones em SVG inline
— mesmo padrão que o `ThemeToggle` já usava antes de existir esse componente
— não uma biblioteca externa. Existe para a navegação parar de ser só texto:
sidebar sem nenhum símbolo ao lado do nome das telas foi o maior sinal de
"rascunho" apontado na revisão visual. Cada ícone é decorativo por padrão
(`aria-hidden`); quem carrega a informação para leitor de tela continua sendo
o texto ao lado.

Os ícones do chat (`paperclip`, `mic`, `send`, `trash`, `stop`) seguem de
propósito a silhueta que todo aplicativo de mensagem usa: ali a familiaridade
vale mais que originalidade — quem abre a conversa precisa reconhecer "anexar"
e "gravar" sem ler nada. Nesses botões o ícone é o único conteúdo, então cada
um leva `aria-label` e `title`, ao contrário dos ícones da navegação.

### Cartão, tabela e badge — acentos que a tela ganhou

- **`.card`** ganhou uma borda de 3px no topo. Neutra por padrão
  (`--border-strong`); as classes de tom (`.ok`/`.warn`/`.danger`, já
  existentes) recolorem essa borda inteira — é o mesmo mecanismo de antes,
  só que agora o resultado é uma faixa visível, não só uma borda fina cinza.
  Cartão clicável (`.card-link`) ganhou elevação no hover.
- **Tabelas tinham um bug de espaçamento**: o modelo antigo zerava
  `padding-left` em toda célula e tirava a folga de uma coluna `.num` do lado
  direito — quando uma coluna numérica vinha seguida de uma coluna de texto
  (`CPA` + `Tokens`, em Campanhas), as duas colavam na tela como
  `CPATokens`, sem espaço nenhum entre elas. O gutter agora é simétrico
  (14px dos dois lados), com a primeira e a última célula compensando para
  ficar rente à borda do painel — mesmo efeito visual de antes, sem colar
  texto de colunas vizinhas. Cabeçalho de tabela também virou caixa alta
  pequena, no mesmo padrão do `.group-title` do Dashboard.
- **Badge de status** ganhou um ponto colorido antes do texto
  (`.badge.ok/.warn/.danger::before`) — o status vira um sinal que se
  reconhece varrendo a coluna com o olho, não só mais uma pílula.

Título de painel (`.panel > h2`) também virou caixa alta pequena. É filho
direto de propósito: um `<h2>` mais fundo no conteúdo — caso do "Como
terminou o atendimento?" em Conversas — é subtítulo de pergunta, não título
de seção, e não deveria virar caixa alta. Quando o título precisa de um
wrapper ao redor (por exemplo ao lado de um badge, em Content.tsx), ele
recebe a classe `.panel-title` para continuar com o mesmo estilo.

### Login

Layout de duas colunas a partir de 900px: painel de marca à esquerda,
formulário à direita — abaixo disso o painel de marca some (`display: none`)
e sobra só o cartão centralizado, que era o único layout que existia antes.
O painel usa gradiente e duas manchas radiais via CSS puro (sem imagem
externa, sem glassmorphism) nas cores da marca. `LoginShell`
(`pages/Login.tsx`) existe só para não duplicar esse painel entre a tela de
login e a de cadastro do 2FA — nenhuma mudança de comportamento em nenhuma
das duas.

### Barra lateral: recolhível no desktop, gaveta no celular

São duas coisas diferentes com aparência parecida, e tratá-las como uma só era
o que quebrava a tela pequena.

**No desktop** a barra recolhe para 64px e mostra só os ícones; a preferência
fica em `localStorage` (`tb_sidebar_compacta`), porque é escolha de tela e não
de sessão — quem recolheu quer recolhido amanhã. O rótulo de cada item passa a
viver no `title`: ícone sozinho, sem nome, é adivinhação.

O botão de recolher fica visível o tempo todo, com moldura própria. A primeira
versão o escondia até o ponteiro chegar na barra, por discrição; o efeito foi
tornar a função inencontrável — ninguém procura um controle que não está na
tela. Recolhida, ele ocupa a linha inteira abaixo da marca (48px úteis não
comportam os dois lado a lado) e a seta gira: ela aponta para onde a ação leva,
não para o estado atual.

**No celular** (≤860px) a barra vira gaveta sobre o conteúdo, aberta pelo
cabeçalho que só existe nessa largura, e sempre começa fechada. Fecha no toque
fora, no ESC e ao navegar. A versão anterior — barra no topo com os oito itens —
empurrava o conteúdo para baixo da dobra. Dentro da gaveta o modo compacto é
ignorado: espaço não falta ali, e "recolhido" é uma decisão de desktop.

### Composição da mensagem (`pages/Conversations.tsx`)

Formato de aplicativo de mensagem, porque é o vocabulário que quem atende já
tem: campo arredondado com o clipe **dentro**, e um único botão redondo à
direita que é microfone enquanto não há nada para enviar e vira avião assim que
há. Antes eram três botões retangulares disputando o mesmo canto — no celular,
isso é erro de alvo.

Durante a gravação, a ordem é a mesma dos mensageiros: descartar à esquerda,
tempo no meio, confirmar à direita. É onde a mão já procura.

Navegador sem `MediaRecorder` (ou página sem HTTPS, onde `getUserMedia` não
existe) não ganha um microfone que falha ao clicar: o lugar fica com o botão de
enviar desabilitado.

### Alvos de toque e o zoom do iOS

No celular os botões do chat vão a 44px e o campo de texto a `font-size: 16px`.
O tamanho não é estética: abaixo de 16px o Safari do iPhone dá zoom ao focar o
campo, e o zoom desalinha a tela inteira, não só o campo.

Tabela estreita demais rola dentro do painel (`overflow-x`), em vez de esticar a
página na horizontal.

### `minmax(0, 1fr)` no login

O grid do login usava `1fr`, que respeita o mínimo automático do conteúdo: o
cartão de 360px mais o respiro da área somavam 408px e produziam rolagem
horizontal em qualquer celular. `minmax(0, 1fr)` deixa a coluna encolher.
A verificação que pega isso é medir `scrollWidth - clientWidth` a 390px de
largura — hoje zero em todas as telas conferidas.

## Telas com regra própria

### Usuários (`src/pages/Operators.tsx`)

Cadastro em modal sobre o `<dialog>` nativo — foco preso, ESC e camada superior
vêm do navegador. O `close` disparado pelo ESC não passa pelo React, então o
`Modal` reemite para o pai; sem isso o estado ficaria "aberto" com a tela já
fechada, e o formulário reabriria com o que foi digitado antes.

Ação destrutiva usa `ConfirmDialog`, não `window.confirm`: o texto precisa nomear
quem será afetado e dizer o que acontece com o histórico — é a diferença entre
desativar e excluir que o usuário tem de ler antes de decidir.

A própria linha do administrador logado mostra só "editar", e o seletor de perfil
vem desabilitado nela. O servidor recusaria de qualquer jeito (409); esconder
evita oferecer um clique que só produziria erro.

### Dashboard (`src/pages/Dashboard.tsx`)

Os indicadores vêm agrupados em **Aquisição**, **Resultado** e **Operação**, e
cada grupo diz a que recorte pertence. O motivo é que `/analytics/overview`
mistura duas naturezas de número: quase tudo é do período, mas
`awaiting_support` conta conversas abertas **agora** (não há filtro de tempo na
consulta). Sete cartões iguais lado a lado faziam o número do momento ser lido
como número do período.

O cartão de taxa de conversão traz a fórmula no rodapé porque numerador e
denominador são coortes diferentes — conversões com `converted_at` no período
sobre leads com `created_at` no período. A conversão de um lead antigo entra num
denominador que não o contém, então o valor pode passar de 100%. Por isso
também não existe barra de progresso nesse cartão: a régua de 0–100% afirmaria
um limite que o dado não respeita.

Cartão vira atalho só quando a listagem consegue reproduzir o mesmo número. O
de leads leva a `/leads?from=<início do período>`; os de qualificados e
conversões não têm link, porque `qualified` soma três status
(`QUALIFIED`, `IN_SUPPORT`, `CONVERTED`) e `conversions` conta registros de
conversão por `converted_at` — nos dois casos a lista de destino mostraria um
total menor que o cartão, o que é pior que não ter link.

O seletor de período (`PeriodPicker`) é o mesmo componente do Funil e do
Analytics. Quando cada tela tinha o seu, mudar o recorte numa e não achar o
controle na outra fazia os números parecerem incoerentes entre telas.

### Funil (`src/pages/Funnel.tsx`)

Cada etapa mostra três leituras: a contagem, quanto sobrou do topo e quanto se
perdeu da etapa anterior. A barra é proporcional à **primeira** etapa, não ao
maior valor da lista — proporcional ao maior, a etapa inicial ficava sempre com
100% da largura e a escala mudava a cada período escolhido.

`analytics_service.funnel` conta usuários distintos por tipo de evento, de forma
independente por etapa: a etapa seguinte **não** é subconjunto da anterior. Logo
uma etapa pode ficar acima da anterior (quem escolheu interesse sem concluir a
qualificação, por exemplo) e `drop_from_previous` chega negativo. A tela trata
esse caso como marcação própria ("acima da anterior") em vez de imprimir queda
negativa, e a largura da barra é limitada a 100%.

O destaque de gargalo usa a maior queda **proporcional** entre etapas
consecutivas, não a maior queda absoluta: no topo o volume é sempre maior e a
primeira transição venceria a comparação em qualquer cenário.

O painel de estados é rotulado "agora" e não acompanha o seletor de período —
`/analytics/states` devolve o estado atual de cada usuário e não aceita `days`.

### Leads (`src/pages/Leads.tsx`)

Os filtros vivem na query string. Voltar do detalhe do lead preserva o recorte,
e o link pode ser passado adiante mostrando a mesma lista. Trocar qualquer
filtro zera a paginação: a página 3 do recorte anterior quase sempre não existe
no recorte novo, e a tela apareceria vazia sem explicação.

A tela expõe o que `GET /leads` já aceitava e ninguém alcançava pela interface:
`campaign_id`, `created_from`, `created_to`, `limit` e `offset`. Antes o texto
da página afirmava existir filtro por campanha que não estava na tela, e a
listagem parava nos primeiros 100 registros sem sinalizar que havia mais.

A lista de campanhas só é buscada para `ADMIN`, `MANAGER` e `ANALYST` — os
perfis com `campaigns:read` no backend. Operador e suporte enxergam leads mas
receberiam 403 em `/campaigns`, então para eles o filtro nem aparece e as
colunas caem para o `#id` da campanha. É gate por perfil observável, não
tratamento de erro depois do fato.

Status aparece traduzido no filtro **e** no badge da tabela, pelo mesmo mapa
(`labels.ts`). O `StatusBadge` recebe a tradução por prop e mantém a cor pelo
código cru: assim as telas que exibem outros domínios de status (conversas,
campanhas) continuam com o texto original.

As datas do filtro viram instante absoluto no fuso do navegador
(`new Date(dia).toISOString()`), não texto sem fuso. São duas correções na
mesma linha: a data pura faria o backend cortar `created_to` em 00:00 e o
último dia escolhido sumiria; e o texto sem fuso seria interpretado como UTC —
em UTC-3, um lead criado às 22:00 caía fora do filtro "criado até" daquele
mesmo dia, porque no relógio do servidor já era o dia seguinte. Verificado no
banco local: com `created_to=2026-08-29T23:59:59` o lead das 22:00 do dia 29
não voltava; com o mesmo dia convertido para `2026-08-30T02:59:59Z`, sim.

O atalho do cartão de leads usa a fronteira do **dia local** (`?from=…`),
enquanto o cartão conta uma janela deslizante de N dias a partir de agora. A
lista pode, portanto, incluir algumas horas a mais que o cartão; é a maior
aproximação possível enquanto o filtro for um campo de data.

## Comandos

```
npm run dev      # servidor de desenvolvimento
npm run lint     # tsc --noEmit
npm run build    # build de produção em dist/
npm run e2e      # fluxo de autenticação em browser real (precisa da stack no ar)
```
