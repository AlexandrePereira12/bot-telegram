# Traffic Bot

Plataforma de aquisição e atendimento para campanhas de tráfego pago que levam ao Telegram.

Quem investe em anúncio para gerar conversa no Telegram costuma perder o rastro do lead no momento
em que ele sai da plataforma de mídia. O clique vira uma mensagem sem origem, o atendimento acontece
solto e a conversão nunca volta para a campanha que a gerou. Este projeto fecha esse ciclo: descobre
de qual anúncio a pessoa veio, conduz a conversa, entrega ao time quando precisa de gente e devolve
o resultado como métrica.

```
Meta/Google Ads → deep link → Telegram → Bot → Funil → Atendimento → Conversão
                                                  ↓
                                         PostgreSQL → Dashboard
```

---

## O que o sistema faz

### Descobre a origem de cada lead

Cada campanha gera um *tracking token* opaco — `t_8Hk92KsL` — que vai no deep link do anúncio. Quando
a pessoa abre a conversa, o backend resolve esse token em campanha → conjunto → anúncio → fonte.
Nada de identificador interno na URL, e cada token pode ser revogado sem afetar os demais.

O lead guarda duas atribuições: **first touch**, imutável, e **last touch**, que acompanha a última
origem conhecida e é o que as métricas de conversão usam. Token inválido, revogado ou ausente não
quebra o fluxo — a pessoa entra como orgânica e o funil segue.

### Conduz o funil como máquina de estados

```
NEW → WELCOME → CONSENT → AGE_GATE → QUALIFICATION → INFORMATION ─┐
                    │          │            │                     ├→ CONVERTED
                    │          │            └→ HUMAN_SUPPORT ──────┘
                    └──────────┴────────────────→ EXIT (terminal)
```

O estado vive no banco, nunca só na memória do processo: reiniciar o bot não perde o progresso de
ninguém. As transições válidas são declaradas num único lugar, e sair de um estado terminal exige
uma operação explícita de reabertura — não é uma transição comum.

### Deixa a conversa ser editada sem tocar em código

Cada campanha pode ter suas próprias mensagens, seus próprios botões e sua própria mídia. Um
criativo de futebol pode abrir uma conversa diferente da de um criativo de música, e a comparação de
conversão entre eles passa a medir *criativo + conversa*, não só o anúncio.

Cada botão do menu define o texto que dispara e para onde leva — responder com um conteúdo ou chamar
atendimento humano. Campanha sem conteúdo próprio herda o padrão global, e o padrão global tem o
código como último recurso: apagar tudo não deixa o bot mudo.

Duas telas ficam de fora dessa flexibilidade de propósito — consentimento e verificação de idade.
Elas têm efeito legal, e o aceite é auditado por versão dos termos: se o texto variasse por campanha,
o registro deixaria de provar o que a pessoa aceitou.

### Passa a conversa para uma pessoa quando precisa

O operador assume a conversa e o bot silencia automaticamente. A resposta sai pelo painel — texto ou
anexo — e é entregue por um worker, então instabilidade do Telegram não derruba a requisição.

Encerrar exige dizer **como terminou**: converteu ou não, com valor e observação opcionais. O
atendimento sai da fila e vai para o histórico. Se o lead voltar a escrever, começa um ciclo novo,
com sua própria conversa e seu próprio desfecho — sem repetir termos nem verificação de idade, e sem
apagar a conversão do ciclo anterior.

É isso que torna respondível "quantos atendimentos deram certo", por operador e por campanha.

### Mede o que aconteceu

Funil por etapa com abandono, conversão por campanha e por anúncio, série temporal, tempo médio até
a conversão, CPL e CPA. Métrica que depende de investimento aparece vazia quando o dado não existe —
nunca como zero, que seria uma resposta errada disfarçada de número.

---

## Arquitetura

| Camada | Tecnologia |
|---|---|
| API | FastAPI · Python 3.12 |
| Bot | aiogram 3 — polling em desenvolvimento, webhook em produção |
| Banco | PostgreSQL 16 · SQLAlchemy 2 · Alembic |
| Cache, filas e locks | Redis 7 |
| Jobs assíncronos | ARQ |
| Painel | React 18 · TypeScript · Vite · TanStack Query · Recharts |
| Proxy | Nginx |
| Empacotamento | Docker Compose |

### O bot é uma interface, não o sistema

Toda regra de negócio vive na camada de serviço. O handler do aiogram traduz entrada e saída e não
decide nada:

```
Telegram → handler → service → repository → PostgreSQL
```

Isso é o que permite acrescentar outro canal — WhatsApp, web, aplicativo — sem reescrever o funil.
E é o que torna as regras testáveis sem subir um bot.

```
backend/app/
├── core/          configuração, banco, segurança, logging, enums
├── models/        17 tabelas
├── services/      funil, tracking, conversão, conteúdo, atendimento, compliance
├── api/routes/    37 endpoints REST
├── bot/           handlers, teclados, middlewares — sem regra de negócio
└── workers/       follow-up, envio, agregação
```

### Um código, muitos clientes

O isolamento entre empresas é físico, não um filtro de query. Cada cliente roda seu próprio
deployment com banco, Redis, bot, domínio e segredos próprios — mesma imagem, `.env` diferente.

```
docker compose -p empresa-a up -d
docker compose -p empresa-b up -d
```

Ainda assim, todas as tabelas carregam `tenant_id` desde a primeira migration. Custa quase nada agora
e deixa a porta aberta para consolidar várias empresas numa infraestrutura só, se um dia fizer
sentido, sem reescrever o schema.

O nome da empresa serve para identificação e configuração — **nunca** para controle de acesso. Essa
separação é deliberada: autorização que depende de um valor de configuração é autorização frágil.

---

## Decisões de segurança

O interessante não é a lista de recursos, e sim por que cada um está do jeito que está.

**O segredo do 2FA só nasce no primeiro acesso.** Gerar na criação do operador significaria fazê-lo
circular por terminal, log e histórico antes de chegar ao dono. Aqui ele é criado quando a pessoa
acerta e-mail e senha pela primeira vez, sai do servidor uma única vez para virar QR no navegador, e
nunca mais é exposto depois de confirmado. Não existe endpoint que devolva a imagem do QR — uma URL
com o segredo dentro vazaria em histórico, log de proxy e header referer.

**Idempotência é uma constraint no PostgreSQL, não um `SETNX` no Redis.** Cache perde a garantia num
restart ou num flush. A verificação também acontece *antes* de qualquer efeito colateral, não depois:
webhook reentregue devolve 200 sem duplicar a conversão, e clicar duas vezes em "encerrar" produz um
registro só.

**O age gate é persistido, não só perguntado.** Quem foi reprovado não volta ao funil reenviando
`/start` — a decisão fica gravada no usuário e é verificada em toda entrada na qualificação,
inclusive depois de uma reabertura de atendimento. É a regra com exposição legal do projeto, então
é a que tem mais teste.

**A validação de compliance mudou de lugar quando os textos saíram do código.** Enquanto as mensagens
eram constantes, um teste varria o módulo garantindo que nenhuma prometia ganho. No momento em que
passaram a ser editáveis pelo painel, esse teste deixaria de cobrir o que importa — então a checagem
virou validação de escrita: texto com promessa de resultado é recusado na API, apontando o termo.

**O papel do operador é relido do banco a cada requisição.** O claim do JWT serve para a interface
decidir o que mostrar; ele não autoriza nada sozinho. Desativar um operador tem efeito imediato, sem
esperar token expirar.

**Só o Nginx é publicado.** PostgreSQL e Redis vivem na rede interna. `/metrics` não é servido
publicamente — um allowlist por IP nessa camada seria inútil, porque atrás do Docker todo cliente
externo chega com o endereço da bridge. A documentação interativa desaparece sozinha em produção.

Além disso: Argon2 para senhas, HMAC-SHA256 com janela de timestamp nos webhooks, rate limiting em
duas camadas, auditoria append-only com IP em hash, e um formatter de log que redige campos sensíveis
antes de escrever.

---

## Como a qualidade é verificada

**112 testes** cobrindo o que quebraria em silêncio: age gate bloqueando reentrada, consentimento
versionado com revogação, idempotência de conversão, RBAC negando escrita ao perfil errado,
assinatura de webhook rejeitando replay e corpo adulterado, resolução de conteúdo por campanha,
e o ciclo de encerrar e reabrir um atendimento.

Boa parte roda **os handlers do bot de verdade**, com dublês no lugar da API do Telegram — testar só
os serviços deixaria passar bugs no caminho que o usuário percorre.

Há também um **teste de navegador** que percorre login, cadastro de 2FA, dashboard, todas as páginas
e logout, falhando se houver qualquer erro no console. Ele existe por um motivo concreto: houve um
bug em que o login respondia 200 enquanto a tela não saía do lugar, e nenhum teste de API pegaria
isso.

Migrations são versionadas e verificadas contra os modelos — o autogenerate do Alembic precisa
acusar zero diferenças.

---

## Estado do projeto

Funcional e exercitado ponta a ponta em ambiente local. O que ainda **não** está pronto:

| Item | Situação |
|---|---|
| Integração com n8n | esqueleto — o job existe, mas nenhum caminho de código o enfileira |
| Dados de mídia (investimento, cliques) | preenchidos à mão; sem sincronização com Meta ou Google Ads |
| Checklist de produção | HTTPS, backup, restore, Prometheus, Grafana e Sentry previstos, não exercitados |
| Revogação de refresh token | o token anterior vale até expirar; o corte imediato é desativar o operador |
| Provisionamento de empresa | procedimento documentado, não automatizado |

---

## Licença

Projeto privado. Todos os direitos reservados.
