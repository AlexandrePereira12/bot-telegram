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

## Comandos

```
npm run dev      # servidor de desenvolvimento
npm run lint     # tsc --noEmit
npm run build    # build de produção em dist/
npm run e2e      # fluxo de autenticação em browser real (precisa da stack no ar)
```
