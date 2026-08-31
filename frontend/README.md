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
