# 🚀 Bot de Tráfego Pago → Telegram

Sistema de aquisição, automação, rastreamento e análise de leads provenientes de campanhas de tráfego pago, com atendimento automatizado via Telegram e dashboard web de métricas.

> **Contexto:** o fluxo foi concebido a partir do documento de planejamento enviado, que define a jornada **anúncio → entrada no Telegram → boas-vindas → qualificação → conversão → CRM/banco → follow-up**, incluindo rastreamento de campanha, etapa do funil e conversão.

> **Compliance:** como os criativos de referência são relacionados a jogos/apostas, o sistema deve operar somente em campanhas, mercados, faixas etárias e comunicações permitidas pelas leis e políticas aplicáveis. O bot não deve prometer ganhos, induzir comportamento compulsivo, contornar restrições de idade ou disparar comunicações sem consentimento/base legal adequada.

---

# 1. Visão do produto

O sistema será uma plataforma própria para controlar o funil de usuários que chegam ao Telegram por meio de anúncios.

```text
                    ┌─────────────────────┐
                    │     TRÁFEGO PAGO    │
                    │ Meta / Google / etc │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      ANÚNCIO        │
                    │ campanha + anúncio  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   TELEGRAM LINK     │
                    │ tracking/deep-link  │
                    └──────────┬──────────┘
                               │
                               ▼
              ┌─────────────────────────────────┐
              │          BOT TELEGRAM            │
              │             aiogram              │
              └────────────────┬────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   FUNIL / ESTADOS   │
                    │ consentimento       │
                    │ idade                │
                    │ qualificação         │
                    │ informação           │
                    │ atendimento          │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
             ┌─────────────┐       ┌─────────────┐
             │ CONVERSÃO   │       │ ATENDIMENTO │
             └──────┬──────┘       └──────┬──────┘
                    │                     │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │     POSTGRESQL      │
                    │ usuários / leads    │
                    │ campanhas / eventos │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
          ┌──────────┐   ┌──────────┐   ┌──────────┐
          │Dashboard │   │Analytics │   │ Integra. │
          │ React    │   │ métricas │   │  n8n     │
          └──────────┘   └──────────┘   └──────────┘
```

---

# 2. Objetivos

## Objetivo principal

Criar uma plataforma capaz de:

- receber usuários provenientes de campanhas;
- identificar a origem do tráfego;
- criar/atualizar o lead;
- conduzir o usuário pelo funil;
- registrar todos os eventos relevantes;
- permitir atendimento humano;
- registrar conversões;
- calcular métricas por campanha, conjunto e anúncio;
- executar automações controladas;
- disponibilizar dashboard web;
- manter segurança, auditoria e governança dos dados.

## Objetivos secundários

- reduzir trabalho manual;
- permitir testes de diferentes campanhas/criativos;
- identificar gargalos do funil;
- centralizar histórico do usuário;
- facilitar integração com outras plataformas;
- permitir crescimento horizontal da aplicação.

---

# 3. Stack tecnológica

## Backend

| Tecnologia | Função |
|---|---|
| Python 3.12+ | linguagem principal |
| FastAPI | API, webhooks e camada HTTP |
| aiogram 3.x | integração com Telegram |
| SQLAlchemy 2.x | ORM |
| Alembic | migrations |
| Pydantic | validação/configuração |
| PostgreSQL | banco principal |
| Redis | cache, locks, filas e estado transitório |
| Celery ou ARQ | jobs assíncronos/scheduled jobs |

### Por que FastAPI?

**Sim. FastAPI é uma excelente escolha para esse projeto.**

O sistema terá:

- muitas operações HTTP/webhook;
- integração com Telegram;
- APIs REST;
- processamento assíncrono;
- dashboard consumindo API;
- webhooks externos;
- autenticação e autorização;
- possibilidade de escalar horizontalmente.

FastAPI já possui suporte para segurança/OAuth2 e mecanismos de background tasks, embora tarefas pesadas ou distribuídas devam usar uma fila/worker dedicado.

**Decisão:** usar FastAPI como **API principal e control plane**, não como sistema responsável por executar todos os jobs pesados.

---

# 4. Arquitetura recomendada

A aplicação será separada em componentes.

```text
                           INTERNET
                              │
                       ┌──────▼──────┐
                       │    NGINX    │
                       │ TLS / proxy │
                       └──────┬──────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
         ┌──────▼──────┐             ┌──────▼──────┐
         │  Dashboard  │             │   FastAPI   │
         │    React    │             │     API     │
         └─────────────┘             └──────┬──────┘
                                            │
                  ┌─────────────────────────┼────────────────────┐
                  │                         │                    │
           ┌──────▼──────┐           ┌──────▼──────┐      ┌──────▼──────┐
           │  PostgreSQL │           │    Redis    │      │   Telegram  │
           │   primary   │           │ cache/queue │      │   aiogram   │
           └─────────────┘           └──────┬──────┘      └─────────────┘
                                            │
                                     ┌──────▼──────┐
                                     │    Worker   │
                                     │ jobs/tasks  │
                                     └─────────────┘

                         Integrações externas
                                  │
                              ┌───▼───┐
                              │  n8n  │
                              └───────┘
```

---

# 5. Responsabilidade de cada componente

## FastAPI

Responsável por:

- REST API;
- autenticação;
- autorização;
- webhooks;
- tracking;
- gerenciamento de campanhas;
- gerenciamento de leads;
- analytics;
- atendimento;
- configurações;
- endpoints administrativos;
- integração com serviços externos.

---

## aiogram

Responsável exclusivamente pela interação com o Telegram:

- recebimento de mensagens;
- comandos;
- callbacks;
- inline keyboards;
- envio de mensagens;
- estados do bot;
- tratamento das interações.

O bot não deve conter regras de negócio complexas.

Exemplo:

```text
Telegram
   ↓
aiogram handler
   ↓
FunnelService
   ↓
PostgreSQL
```

---

## PostgreSQL

Fonte principal da verdade.

Armazena:

- usuários;
- leads;
- campanhas;
- anúncios;
- sessões;
- estados;
- eventos;
- mensagens;
- conversas;
- conversões;
- consentimentos;
- auditoria.

---

## Redis

Usado para dados transitórios e operações rápidas:

- cache;
- rate limiting;
- locks;
- idempotência;
- filas;
- estado temporário;
- controle de jobs.

Redis não deve substituir o PostgreSQL como fonte definitiva dos dados.

---

## Worker

Executa tarefas que não precisam bloquear a API:

- follow-ups;
- processamento de eventos;
- envio de mensagens;
- sincronizações;
- agregações;
- integrações externas;
- tarefas agendadas;
- retries.

---

# 6. n8n: precisamos?

## Resposta curta

**Não para o núcleo do sistema.**

Eu não colocaria o n8n como dependência central do bot.

### Arquitetura recomendada

```text
             CORE
              │
     ┌────────┼────────┐
     ▼        ▼        ▼
 FastAPI  PostgreSQL  Redis
     │
   aiogram
     │
 Telegram
```

E o n8n como camada complementar:

```text
              SISTEMA
                 │
              Webhooks
                 │
                 ▼
                n8n
       ┌─────────┼─────────┐
       ▼         ▼         ▼
     CRM       E-mail    Slack
     Sheets    Alertas   Outros
```

## Quando usar n8n

Usaria n8n para:

- enviar dados para CRM;
- receber webhooks externos;
- enviar notificações;
- integrar Google Sheets;
- integrar Slack/Discord;
- automações administrativas;
- sincronizações;
- workflows que mudam com frequência;
- integrações que não justificam código próprio.

## Quando NÃO usar n8n

Não colocaria no n8n:

- máquina de estados do bot;
- autenticação principal;
- autorização;
- regras críticas do funil;
- tracking principal;
- controle de consentimento;
- lógica de conversão;
- persistência principal;
- processamento crítico.

### Motivo

Se o n8n cair, o bot precisa continuar funcionando.

```text
n8n OFF

Bot Telegram ────────────────► CONTINUA FUNCIONANDO
FastAPI ─────────────────────► CONTINUA FUNCIONANDO
PostgreSQL ──────────────────► CONTINUA FUNCIONANDO
Dashboard ───────────────────► CONTINUA FUNCIONANDO

Integrações externas ────────► podem ficar pendentes
```

Isso evita criar um ponto único de falha.

---

# 7. Modelo de dados

## users

```text
users
--------------------------------
id
telegram_id UNIQUE
username
first_name
language
current_state
age_confirmed
consent_status
is_blocked
created_at
updated_at
```

## campaigns

```text
campaigns
--------------------------------
id
external_id
name
source
platform
status
created_at
updated_at
```

## ad_sets

```text
ad_sets
--------------------------------
id
campaign_id
external_id
name
status
created_at
```

## ads

```text
ads
--------------------------------
id
ad_set_id
external_id
name
creative
status
created_at
```

## leads

```text
leads
--------------------------------
id
user_id
campaign_id
ad_set_id
ad_id
source
first_touch_campaign_id
last_touch_campaign_id
status
created_at
converted_at
```

## events

```text
events
--------------------------------
id
user_id
lead_id
event_type
metadata JSONB
created_at
```

## conversations

```text
conversations
--------------------------------
id
user_id
status
assigned_to
started_at
ended_at
```

## messages

```text
messages
--------------------------------
id
conversation_id
telegram_message_id
direction
message_type
content
created_at
```

## conversions

```text
conversions
--------------------------------
id
lead_id
external_id
conversion_type
value
currency
metadata JSONB
converted_at
```

## consent_records

```text
consent_records
--------------------------------
id
user_id
consent_type
version
accepted
source
ip_hash
created_at
revoked_at
```

## audit_logs

```text
audit_logs
--------------------------------
id
actor_id
action
resource_type
resource_id
metadata JSONB
ip_hash
created_at
```

---

# 8. Máquina de estados do bot

O bot será implementado como uma **Finite State Machine**.

```text
NEW
 │
 ▼
WELCOME
 │
 ▼
CONSENT
 │
 ▼
AGE_GATE
 │
 ├──────────────► EXIT
 │
 ▼
QUALIFICATION
 │
 ├────────► INFORMATION
 │
 ├────────► HUMAN_SUPPORT
 │
 └────────► EXIT
                  │
                  ▼
              CONVERTED
```

Os estados devem ser persistidos.

Nunca depender somente da memória do processo.

---

# 9. Eventos

O sistema será orientado a eventos para permitir analytics.

Exemplos:

```text
USER_STARTED
WELCOME_SENT
CONSENT_VIEWED
CONSENT_ACCEPTED
AGE_CONFIRMED
AGE_REJECTED
QUALIFICATION_STARTED
QUALIFICATION_COMPLETED
INTEREST_SELECTED
FAQ_OPENED
HUMAN_SUPPORT_REQUESTED
MESSAGE_SENT
MESSAGE_RECEIVED
FOLLOWUP_SCHEDULED
FOLLOWUP_SENT
CONVERSION
USER_BLOCKED
CONSENT_REVOKED
```

Cada evento deve possuir:

```json
{
  "user_id": 123,
  "event_type": "QUALIFICATION_COMPLETED",
  "campaign_id": "camp_001",
  "metadata": {
    "answer": "information"
  }
}
```

---

# 10. Rastreamento de campanhas

O tracking precisa responder:

> De onde esse usuário veio?

A estrutura recomendada:

```text
Plataforma
   ↓
Campanha
   ↓
Conjunto
   ↓
Anúncio
   ↓
Criativo
   ↓
Telegram
   ↓
Usuário
   ↓
Lead
   ↓
Conversão
```

## First touch

Primeira origem conhecida.

## Last touch

Última origem conhecida antes da conversão.

Guardar os dois permite análises posteriores.

---

# 11. Funil

O dashboard deverá permitir visualizar:

```text
ENTRADAS
100.000
    │
    ▼
CONSENTIMENTOS
2.500
    │
    ▼
QUALIFICADOS
1.500
    │
    ▼
INTERESSADOS
900
    │
    ▼
CONVERSÕES
120
```

O exemplo acima acompanha a estrutura de funil apresentada no documento enviado.

---

# 12. Dashboard web

## Stack

```text
React
Vite
TypeScript
React Router
TanStack Query
ECharts/Recharts
```

## Páginas

### Dashboard

```text
/dashboard
```

Indicadores:

```text
Usuários
Leads
Qualificados
Conversões
Taxa de conversão
```

---

### Campanhas

```text
/campaigns
```

Mostrar:

```text
Campanha
Fonte
Investimento
Impressões
Cliques
Leads
Conversões
Custo por lead
Custo por conversão
ROI
```

> Custos e ROI só serão calculados se os dados de investimento estiverem disponíveis via API/importação.

---

### Funil

```text
/funnel
```

Visual:

```text
Entradas
   ↓
Consentimento
   ↓
Qualificação
   ↓
Interesse
   ↓
Atendimento
   ↓
Conversão
```

---

### Leads

```text
/leads
```

Filtros:

```text
campanha
fonte
status
data
estado atual
```

---

### Conversas

```text
/conversations
```

Permite:

- visualizar conversa;
- assumir atendimento;
- devolver para automação;
- consultar histórico;
- consultar origem do lead.

---

### Analytics

```text
/analytics
```

Gráficos:

- usuários por dia;
- leads por campanha;
- conversão por campanha;
- conversão por anúncio;
- abandono por etapa;
- tempo médio até conversão;
- origem dos usuários;
- desempenho por período.

---

# 13. Arquitetura do dashboard

```text
React
 │
 ▼
TanStack Query
 │
 ▼
FastAPI
 │
 ├── /auth
 ├── /campaigns
 ├── /leads
 ├── /events
 ├── /conversations
 ├── /analytics
 └── /admin
       │
       ▼
   PostgreSQL
```

O frontend nunca acessará o PostgreSQL diretamente.

---

# 14. Segurança

Segurança será requisito de arquitetura, não uma etapa posterior.

## 14.1 Rede

```text
Internet
   │
   ▼
Nginx
   │
   ▼
FastAPI
   │
   ├── PostgreSQL
   └── Redis
```

PostgreSQL e Redis:

**NÃO devem ficar expostos diretamente à internet.**

---

## 14.2 HTTPS

Toda comunicação externa deverá usar HTTPS.

```text
HTTP → redirect → HTTPS
```

---

## 14.3 Secrets

Nunca colocar tokens no Git.

```env
TELEGRAM_BOT_TOKEN=
DATABASE_URL=
REDIS_URL=
JWT_SECRET=
ENCRYPTION_KEY=
```

Produção deverá utilizar secret manager quando possível.

---

# 15. Autenticação

Dashboard terá autenticação própria.

Recomendação:

```text
Access Token
+
Refresh Token
+
RBAC
+
2FA
```

Perfis:

```text
ADMIN
MANAGER
OPERATOR
ANALYST
SUPPORT
```

Exemplo:

```text
ADMIN
 └── tudo

MANAGER
 ├── campanhas
 ├── leads
 └── analytics

ANALYST
 └── analytics

SUPPORT
 └── conversas
```

---

# 16. Rate limiting

Precisamos proteger:

```text
POST /auth/login
POST /webhooks/*
POST /events
Telegram handlers
```

Exemplo conceitual:

```text
IP
 ↓
Rate limiter
 ↓
API
```

Redis pode controlar os limites.

---

# 17. Idempotência

Webhooks e eventos podem ser recebidos mais de uma vez.

Nunca executar duas vezes uma operação crítica.

Exemplo:

```text
event_id = abc123
```

Se:

```text
abc123 já processado
```

então:

```text
HTTP 200
sem executar novamente
```

---

# 18. Segurança dos webhooks

Todo webhook externo deverá possuir:

- assinatura quando disponível;
- secret;
- validação de origem quando possível;
- timestamp;
- proteção contra replay;
- idempotency key;
- logs;
- rate limit.

Exemplo:

```text
POST /webhooks/provider

X-Signature: ...
X-Timestamp: ...
X-Idempotency-Key: ...
```

---

# 19. Auditoria

Ações administrativas precisam ser registradas.

Exemplo:

```text
ADMIN
 ↓
ALTEROU CAMPANHA
 ↓
audit_logs
```

Registrar:

```text
quem
o quê
quando
recurso
IP hash
resultado
```

Nunca registrar secrets ou tokens nos logs.

---

# 20. Proteção de dados

O sistema deverá possuir mecanismos para:

- consentimento;
- revogação;
- exportação quando aplicável;
- exclusão quando aplicável;
- retenção;
- controle de acesso;
- minimização de dados;
- auditoria.

Dados sensíveis não devem ser armazenados sem necessidade.

---

# 21. Observabilidade

A aplicação deverá possuir:

```text
Logs
Metrics
Tracing
Error tracking
Health checks
```

## Stack sugerida

```text
Prometheus
Grafana
Sentry
```

Endpoints:

```text
GET /health
GET /ready
GET /metrics
```

---

# 22. Health check

Exemplo:

```text
/health

API: OK
PostgreSQL: OK
Redis: OK
Telegram: OK
Workers: OK
```

---

# 23. Tratamento de erros

Nenhum erro externo deve derrubar o bot.

Exemplo:

```text
Telegram API
     │
     X
     │
Retry
     │
     ▼
Redis Queue
     │
     ▼
Worker
```

Estratégia:

```text
retry 1
   ↓
retry 2
   ↓
retry 3
   ↓
dead-letter/error queue
```

---

# 24. Jobs assíncronos

Não usar:

```python
await tarefa_pesada()
```

dentro de uma requisição que precisa responder rapidamente.

Fluxo:

```text
API
 ↓
Redis
 ↓
Worker
 ↓
Processamento
```

Exemplos:

```text
send_followup
sync_campaign
process_conversion
aggregate_metrics
send_notification
```

---

# 25. n8n + sistema

Quando houver necessidade de integração:

```text
FastAPI
   │
   ▼
Webhook
   │
   ▼
n8n
   │
   ├── CRM
   ├── Google Sheets
   ├── Slack
   ├── E-mail
   └── outras APIs
```

O n8n deve ser tratado como **integration layer**, não como backend principal.

---

# 26. Docker

Serviços locais:

```text
docker-compose.yml

services:

  api
  bot
  worker
  postgres
  redis
  nginx
  frontend
  n8n
```

Em desenvolvimento, n8n pode ficar opcional:

```text
docker compose --profile integrations up
```

---

# 27. Estrutura do projeto

```text
traffic-bot/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   │
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── campaign.py
│   │   │   ├── ad.py
│   │   │   ├── lead.py
│   │   │   ├── event.py
│   │   │   ├── conversion.py
│   │   │   ├── conversation.py
│   │   │   ├── consent.py
│   │   │   └── audit.py
│   │   │
│   │   ├── schemas/
│   │   │
│   │   ├── api/
│   │   │   └── routes/
│   │   │
│   │   ├── bot/
│   │   │   ├── bot.py
│   │   │   ├── handlers/
│   │   │   ├── keyboards/
│   │   │   ├── states/
│   │   │   └── middlewares/
│   │   │
│   │   ├── services/
│   │   │   ├── funnel_service.py
│   │   │   ├── tracking_service.py
│   │   │   ├── lead_service.py
│   │   │   ├── campaign_service.py
│   │   │   ├── conversion_service.py
│   │   │   └── conversation_service.py
│   │   │
│   │   ├── workers/
│   │   │   ├── tasks.py
│   │   │   └── scheduler.py
│   │   │
│   │   └── repositories/
│   │
│   ├── migrations/
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── stores/
│   │   └── types/
│   ├── Dockerfile
│   └── package.json
│
├── n8n/
│   └── workflows/
│
├── nginx/
│   └── nginx.conf
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

# 28. API inicial

## Auth

```http
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
```

## Campaigns

```http
GET    /api/v1/campaigns
POST   /api/v1/campaigns
GET    /api/v1/campaigns/{id}
PATCH  /api/v1/campaigns/{id}
```

## Leads

```http
GET /api/v1/leads
GET /api/v1/leads/{id}
```

## Events

```http
POST /api/v1/events
GET  /api/v1/events
```

## Conversations

```http
GET  /api/v1/conversations
GET  /api/v1/conversations/{id}
POST /api/v1/conversations/{id}/assign
POST /api/v1/conversations/{id}/messages
```

## Analytics

```http
GET /api/v1/analytics/overview
GET /api/v1/analytics/funnel
GET /api/v1/analytics/campaigns
GET /api/v1/analytics/ads
GET /api/v1/analytics/timeseries
```

## Webhooks

```http
POST /api/v1/webhooks/telegram
POST /api/v1/webhooks/conversion
POST /api/v1/webhooks/external/{provider}
```

---

# 29. Fluxo de entrada

Exemplo:

```text
Usuário vê anúncio
       ↓
Clica
       ↓
Telegram
       ↓
/start <tracking_token>
       ↓
Backend valida token
       ↓
Localiza campanha
       ↓
Cria/atualiza usuário
       ↓
Cria/atualiza lead
       ↓
Registra USER_STARTED
       ↓
WELCOME
```

---

# 30. Tracking token

Não colocar informações sensíveis diretamente no parâmetro do Telegram.

Preferir:

```text
/start t_8Hk92KsL
```

O backend resolve:

```text
t_8Hk92KsL
       ↓
campaign_id
ad_set_id
ad_id
source
```

Isso evita expor dados internos e facilita revogar tokens.

---

# 31. Métricas principais

## Aquisição

```text
visitas
entradas
novos usuários
usuários por fonte
usuários por campanha
usuários por anúncio
```

## Funil

```text
entrada
consentimento
idade confirmada
qualificação
interesse
atendimento
conversão
abandono
```

## Conversão

```text
conversion rate
tempo até conversão
conversões por campanha
conversões por anúncio
```

## Operação

```text
mensagens enviadas
mensagens recebidas
tempo de atendimento
conversas abertas
conversas encerradas
erros
jobs falhos
```

---

# 32. Métricas financeiras

Caso os dados de mídia estejam disponíveis:

```text
spend
CPC
CPM
CPL
CPA
ROAS
ROI
```

Exemplo:

```text
CPL = investimento / leads
CPA = investimento / conversões
```

Não assumir esses dados se a plataforma de anúncios não fornecê-los.

---

# 33. Segurança operacional

Checklist mínimo antes de produção:

```text
[ ] HTTPS
[ ] Secrets fora do Git
[ ] PostgreSQL privado
[ ] Redis privado
[ ] Firewall
[ ] Rate limiting
[ ] RBAC
[ ] 2FA para administradores
[ ] Auditoria
[ ] Backup automático
[ ] Teste de restore
[ ] Logs
[ ] Monitoramento
[ ] Alertas
[ ] Webhook signatures
[ ] Idempotência
[ ] Proteção contra replay
[ ] Validação de entrada
[ ] Dependências atualizadas
[ ] SAST
[ ] Dependency scanning
[ ] Container scanning
```

---

# 34. Testes

## Unitários

```text
pytest
```

Testar:

- regras do funil;
- tracking;
- atribuição;
- conversão;
- permissões;
- validações.

## Integração

```text
PostgreSQL
Redis
Telegram mock
```

## E2E

Fluxo:

```text
/start
 ↓
consentimento
 ↓
idade
 ↓
qualificação
 ↓
atendimento
 ↓
conversão
```

---

# 35. CI/CD

Pipeline:

```text
Git Push
   ↓
GitHub Actions
   │
   ├── lint
   ├── type check
   ├── tests
   ├── security scan
   ├── build
   └── deploy
```

Ferramentas:

```text
ruff
mypy
pytest
pip-audit
Trivy
```

---

# 36. Ambientes

Ter pelo menos:

```text
development
staging
production
```

Nunca desenvolver diretamente em produção.

Fluxo:

```text
feature
   ↓
development
   ↓
staging
   ↓
production
```

---

# 37. Escalabilidade

Inicialmente:

```text
1 API
1 Bot
1 Worker
1 PostgreSQL
1 Redis
```

Depois:

```text
             Load Balancer
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
      API 1     API 2     API 3
        │         │         │
        └─────────┼─────────┘
                  ▼
                Redis
                  │
          ┌───────┼───────┐
          ▼       ▼       ▼
       Worker1 Worker2 Worker3
                  │
                  ▼
              PostgreSQL
```

---

# 38. Princípio arquitetural principal

A regra mais importante:

> **O bot não deve ser o sistema. O bot é apenas uma interface do sistema.**

A lógica pertence ao backend.

```text
Telegram
   │
aiogram
   │
Service Layer
   │
Repository
   │
PostgreSQL
```

Isso permite futuramente adicionar:

```text
Telegram
WhatsApp
Web
App
```

sem reescrever toda a lógica.

---

# 39. Roadmap

## Fase 1 — Fundação

- [ ] criar repositório;
- [ ] Docker;
- [ ] FastAPI;
- [ ] PostgreSQL;
- [ ] Redis;
- [ ] Alembic;
- [ ] configuração;
- [ ] logging.

## Fase 2 — Bot

- [ ] aiogram;
- [ ] webhook;
- [ ] `/start`;
- [ ] deep link;
- [ ] estados;
- [ ] keyboards;
- [ ] mensagens.

## Fase 3 — Tracking

- [ ] campanhas;
- [ ] conjuntos;
- [ ] anúncios;
- [ ] tracking token;
- [ ] first touch;
- [ ] last touch;
- [ ] eventos.

## Fase 4 — CRM

- [ ] leads;
- [ ] histórico;
- [ ] conversas;
- [ ] atendimento humano.

## Fase 5 — Dashboard

- [ ] login;
- [ ] RBAC;
- [ ] dashboard;
- [ ] campanhas;
- [ ] leads;
- [ ] funil;
- [ ] analytics.

## Fase 6 — Automação

- [ ] workers;
- [ ] jobs;
- [ ] follow-up;
- [ ] retries;
- [ ] integrações.

## Fase 7 — n8n

- [ ] instalar opcionalmente;
- [ ] webhooks;
- [ ] CRM;
- [ ] notificações;
- [ ] integrações externas.

## Fase 8 — Produção

- [ ] HTTPS;
- [ ] firewall;
- [ ] backups;
- [ ] monitoring;
- [ ] Sentry;
- [ ] Prometheus;
- [ ] Grafana;
- [ ] security audit;
- [ ] disaster recovery.

---

# 68. Decisão tecnológica final

| Componente | Escolha |
|---|---|
| Linguagem | **Python** |
| API | **FastAPI** |
| Telegram | **aiogram** |
| Banco | **PostgreSQL** |
| Cache/Queue | **Redis** |
| Jobs | **Celery/ARQ** |
| Frontend | **React + TypeScript** |
| Proxy | **Nginx** |
| Containers | **Docker** |
| CI/CD | **GitHub Actions** |
| Monitoramento | **Prometheus + Grafana** |
| Error tracking | **Sentry** |
| Integrações | **n8n opcional** |
| Testes | **Pytest** |
| Migrations | **Alembic** |

---

# 41. Decisão sobre n8n

## MVP

**Não é obrigatório.**

Começar:

```text
FastAPI
+
aiogram
+
PostgreSQL
+
Redis
+
Worker
+
React
```

## Depois

Adicionar:

```text
n8n
```

somente quando surgirem integrações que justifiquem.

Isso mantém o núcleo:

- testável;
- versionável;
- previsível;
- seguro;
- independente de uma ferramenta externa.

---

# 42. MVP recomendado

A primeira versão que eu implementaria seria:

```text
                    META/ADS
                       │
                       ▼
                  TRACKING LINK
                       │
                       ▼
                    TELEGRAM
                       │
                       ▼
                     BOT
                       │
              ┌────────┴────────┐
              ▼                 ▼
          POSTGRES            REDIS
              │                 │
              └────────┬────────┘
                       ▼
                    FASTAPI
                       │
                       ▼
                   DASHBOARD
```

Com apenas:

```text
1. /start
2. tracking
3. usuário
4. lead
5. campanha
6. eventos
7. estados
8. consentimento/idade
9. dashboard básico
10. autenticação
11. logs
12. segurança
```

Depois evoluímos para:

```text
CRM
↓
Atendimento
↓
Jobs
↓
Follow-up
↓
Conversões
↓
Analytics avançado
↓
n8n
↓
Escala
```

---

# 43. Resultado esperado

Ao final, o sistema deverá responder em tempo real perguntas como:

> Quantos usuários entraram hoje?

> Qual campanha trouxe mais usuários?

> Qual anúncio teve maior conversão?

> Em qual etapa os usuários abandonam o funil?

> Quantos leads estão aguardando atendimento?

> Qual foi o custo por lead?

> Quantas conversões vieram de cada campanha?

> Quanto tempo levou entre entrada e conversão?

> Quais integrações falharam?

Tudo isso sem depender do n8n para o funcionamento do núcleo.

---

# 44. Referências técnicas

- FastAPI — API, segurança, deployment e background tasks.
- aiogram — integração assíncrona com Telegram.
- PostgreSQL — persistência.
- Redis — cache/filas/locks.
- React — dashboard.
- n8n — integrações e automações externas.



---

# 45. Arquitetura Multiempresa / Multi-Cliente

O sistema não será desenvolvido pensando em apenas uma empresa.

A arquitetura deve permitir que o **mesmo código-fonte seja utilizado por várias empresas**, mantendo os dados, credenciais, bots, campanhas e operações de cada empresa isolados.

A estratégia inicial recomendada é:

> **um deployment isolado por empresa**, utilizando a mesma imagem/código da aplicação.

Isso é diferente de colocar todas as empresas no mesmo banco.

## Modelo

```text
                    REPOSITÓRIO / CÓDIGO ÚNICO
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
        EMPRESA A         EMPRESA B         EMPRESA C
        deployment        deployment        deployment
             │                │                │
       ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴─────┐
       │ Docker    │    │ Docker    │    │ Docker    │
       │ PostgreSQL│    │ PostgreSQL│    │ PostgreSQL│
       │ Redis     │    │ Redis     │    │ Redis     │
       │ API       │    │ API       │    │ API       │
       │ Bot       │    │ Bot       │    │ Bot       │
       │ Frontend  │    │ Frontend  │    │ Frontend  │
       └───────────┘    └───────────┘    └───────────┘
```

Cada empresa terá seu próprio ambiente.

---

# 46. Princípio de isolamento

A empresa A não deve conseguir acessar:

- banco da empresa B;
- Redis da empresa B;
- bot da empresa B;
- campanhas da empresa B;
- leads da empresa B;
- conversas da empresa B;
- tokens da empresa B;
- dashboard da empresa B.

Exemplo:

```text
EMPRESA A

company-a/
├── api
├── bot
├── frontend
├── postgres
└── redis


EMPRESA B

company-b/
├── api
├── bot
├── frontend
├── postgres
└── redis
```

Mesmo que as duas utilizem exatamente a mesma versão do código.

---

# 47. Nome da empresa via `.env`

Cada deployment possuirá suas próprias variáveis de ambiente.

### Empresa A

```env
COMPANY_NAME=Empresa A
COMPANY_SLUG=empresa-a

APP_ENV=production

TELEGRAM_BOT_TOKEN=...
DATABASE_URL=...
REDIS_URL=...

API_DOMAIN=api.empresa-a.com
WEB_DOMAIN=app.empresa-a.com
```

### Empresa B

```env
COMPANY_NAME=Empresa B
COMPANY_SLUG=empresa-b

APP_ENV=production

TELEGRAM_BOT_TOKEN=...
DATABASE_URL=...
REDIS_URL=...

API_DOMAIN=api.empresa-b.com
WEB_DOMAIN=app.empresa-b.com
```

O código da aplicação continua sendo o mesmo.

---

# 48. Não utilizar `COMPANY_NAME` como mecanismo de segurança

O nome da empresa serve para **configuração e identificação**, não para controle de acesso.

Não fazer:

```python
if company_name == "empresa-a":
    allow_access()
```

A separação de segurança vem da infraestrutura e das credenciais:

```text
Empresa A
    │
    ├── PostgreSQL A
    ├── Redis A
    ├── Bot Token A
    └── Secrets A

Empresa B
    │
    ├── PostgreSQL B
    ├── Redis B
    ├── Bot Token B
    └── Secrets B
```

---

# 49. Docker por empresa

O `docker-compose.yml` será genérico.

Exemplo conceitual:

```yaml
services:

  api:
    image: traffic-bot:latest
    env_file:
      - .env

  bot:
    image: traffic-bot:latest
    env_file:
      - .env

  worker:
    image: traffic-bot:latest
    env_file:
      - .env

  frontend:
    image: traffic-dashboard:latest

  postgres:
    image: postgres:16

  redis:
    image: redis:7

  nginx:
    image: nginx:alpine
```

A configuração muda pelo `.env`, não pelo código.

---

# 50. Docker Compose Project Name

Cada empresa deve possuir um nome de projeto Docker independente.

Exemplo:

```bash
docker compose -p empresa-a up -d
```

e:

```bash
docker compose -p empresa-b up -d
```

Isso evita colisões de nomes de containers, redes e volumes.

Estrutura no servidor:

```text
/opt/traffic-bot/

├── empresa-a/
│   ├── .env
│   ├── docker-compose.yml
│   └── backups/
│
├── empresa-b/
│   ├── .env
│   ├── docker-compose.yml
│   └── backups/
│
└── empresa-c/
    ├── .env
    ├── docker-compose.yml
    └── backups/
```

---

# 51. Volumes isolados

Cada empresa deverá possuir volumes próprios.

```text
empresa-a-postgres
empresa-a-redis

empresa-b-postgres
empresa-b-redis
```

Nunca compartilhar o volume do PostgreSQL entre empresas.

---

# 52. Banco de dados por empresa

A recomendação inicial é:

> **1 PostgreSQL por empresa/deployment.**

Isso proporciona isolamento forte e simplifica:

- backup;
- restore;
- migração;
- exclusão;
- auditoria;
- troubleshooting;
- portabilidade;
- disaster recovery.

Exemplo:

```text
Empresa A
   └── PostgreSQL A
        ├── users
        ├── leads
        ├── campaigns
        ├── events
        └── conversions

Empresa B
   └── PostgreSQL B
        ├── users
        ├── leads
        ├── campaigns
        ├── events
        └── conversions
```

---

# 53. `tenant_id` no modelo

Mesmo utilizando banco isolado por empresa, recomendo manter um conceito de `tenant_id` na arquitetura.

Motivo:

A aplicação fica preparada para uma futura mudança para:

```text
Multi-tenant
```

caso, em algum momento, seja interessante hospedar várias empresas em uma mesma infraestrutura.

Porém:

> **`tenant_id` não substitui o isolamento físico atual.**

Na primeira arquitetura:

```text
tenant/company
       │
       ▼
deployment isolado
       │
       ▼
database isolado
```

No futuro, poderíamos suportar:

```text
                 PostgreSQL Cluster
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      tenant A     tenant B     tenant C
```

sem precisar reescrever toda a aplicação.

---

# 54. Configuração centralizada

Criar um objeto de configuração:

```python
class Settings(BaseSettings):

    company_name: str
    company_slug: str

    app_env: str

    telegram_bot_token: str

    database_url: str
    redis_url: str

    api_domain: str
    web_domain: str
```

O sistema inteiro utiliza `Settings`.

Não espalhar:

```python
os.getenv(...)
```

por dezenas de arquivos.

---

# 55. Identidade da empresa

A empresa deverá aparecer no dashboard:

```text
┌────────────────────────────────────┐
│  EMPRESA A                         │
│                                    │
│  Dashboard                         │
│  Campanhas                         │
│  Leads                             │
│  Conversões                        │
│  Atendimento                       │
└────────────────────────────────────┘
```

O mesmo frontend funciona para qualquer cliente.

---

# 56. Dashboard multiempresa

Na arquitetura inicial, cada empresa possui seu próprio dashboard:

```text
https://app.empresa-a.com
```

e:

```text
https://app.empresa-b.com
```

Cada domínio aponta para o deployment correspondente.

Isso reduz significativamente o risco de vazamento entre clientes.

---

# 57. Futuro: painel da plataforma

Se o projeto crescer e virar um produto SaaS, podemos adicionar um painel administrativo separado:

```text
                 PLATFORM ADMIN
                       │
                       ▼
               ┌───────────────┐
               │ Tenant Manager│
               └───────┬───────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    Empresa A       Empresa B      Empresa C
```

Esse painel poderia administrar:

- empresas;
- deployments;
- status;
- versões;
- planos;
- domínios;
- licenças;
- monitoramento;
- provisionamento.

Esse componente **não precisa existir no MVP**.

---

# 58. Provisionamento de uma nova empresa

A criação de um novo cliente deverá ser previsível.

Fluxo:

```text
Nova empresa
     │
     ▼
Criar diretório
     │
     ▼
Gerar `.env`
     │
     ▼
Configurar domínio
     │
     ▼
Configurar Telegram Bot
     │
     ▼
Subir Docker Compose
     │
     ▼
Executar migrations
     │
     ▼
Criar usuário administrador
     │
     ▼
Health check
     │
     ▼
EMPRESA ONLINE
```

Idealmente isso será posteriormente automatizado.

---

# 59. Versionamento

Todas as empresas devem utilizar imagens versionadas.

Evitar:

```text
latest
```

em produção.

Preferir:

```text
traffic-bot:1.4.0
```

Assim:

```text
Empresa A → 1.4.0
Empresa B → 1.4.0
Empresa C → 1.3.2
```

permitindo atualização controlada.

---

# 60. Atualização de uma empresa

Fluxo:

```text
Nova versão
    │
    ▼
CI/CD
    │
    ▼
Build image
    │
    ▼
Testes
    │
    ▼
Staging
    │
    ▼
Backup
    │
    ▼
Deploy Empresa A
    │
    ▼
Health check
    │
    ├── OK → concluído
    │
    └── FAIL → rollback
```

Não atualizar todos os clientes simultaneamente sem necessidade.

---

# 61. Segurança multiempresa

Cada deployment terá:

```text
Bot Token próprio
JWT Secret próprio
Database próprio
Redis próprio
Encryption Key própria
Backup próprio
Logs próprios
Domínio próprio
```

Nunca compartilhar secrets entre empresas.

Exemplo:

```text
empresa-a/.env
    TELEGRAM_BOT_TOKEN=A
    JWT_SECRET=A
    ENCRYPTION_KEY=A

empresa-b/.env
    TELEGRAM_BOT_TOKEN=B
    JWT_SECRET=B
    ENCRYPTION_KEY=B
```

---

# 62. Backups

Cada empresa terá backup independente.

```text
backups/
├── empresa-a/
│   ├── 2026-08-28.sql.gz
│   └── 2026-08-29.sql.gz
│
├── empresa-b/
│   ├── 2026-08-28.sql.gz
│   └── 2026-08-29.sql.gz
```

O processo de restore também deverá ser independente.

---

# 63. Logs

Logs também devem conter contexto da empresa.

Exemplo:

```json
{
  "company": "empresa-a",
  "service": "bot",
  "event": "USER_STARTED",
  "user_id": 123
}
```

Nunca colocar tokens ou secrets nos logs.

---

# 64. Monitoramento

No início, cada deployment poderá possuir seus próprios health checks.

Em uma infraestrutura maior, um monitoramento central poderá acompanhar:

```text
                    MONITORING
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
     Empresa A       Empresa B       Empresa C
        │               │               │
       API             API             API
       Bot             Bot             Bot
       DB              DB              DB
```

Alertas:

```text
API DOWN
BOT DOWN
DATABASE DOWN
REDIS DOWN
WORKER DOWN
HIGH ERROR RATE
DISK FULL
BACKUP FAILURE
```

---

# 65. Por que essa arquitetura?

Essa abordagem oferece três vantagens importantes:

### 1. Isolamento

Um problema em uma empresa não precisa afetar outra.

### 2. Segurança

Os dados dos clientes ficam fisicamente separados por deployment/banco.

### 3. Escalabilidade comercial

Podemos adicionar clientes sem criar uma nova aplicação.

O que muda é:

```text
.env
+
infraestrutura
```

e não o código.

---

# 66. Arquitetura final multiempresa

```text
                         GITHUB
                           │
                           │
                    ┌──────▼──────┐
                    │  CODEBASE   │
                    │    ÚNICO    │
                    └──────┬──────┘
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼

        EMPRESA A      EMPRESA B      EMPRESA C
        ─────────      ─────────      ─────────
        .env           .env           .env
          │              │              │
        Docker         Docker         Docker
          │              │              │
       ┌──┴──┐         ┌──┴──┐         ┌──┴──┐
       │ API │         │ API │         │ API │
       │ BOT │         │ BOT │         │ BOT │
       │ WEB │         │ WEB │         │ WEB │
       │ DB  │         │ DB  │         │ DB  │
       │REDIS│         │REDIS│         │REDIS│
       └─────┘         └─────┘         └─────┘
```

---

# 67. Decisão arquitetural

A partir deste ponto, o projeto será tratado como:

> **uma plataforma de automação de tráfego e atendimento multiempresa, com deployments isolados por cliente e codebase compartilhado.**

### Regra principal

```text
1 CODEBASE
     +
N DEPLOYMENTS
     +
1 ENV POR EMPRESA
     +
1 BANCO POR EMPRESA
     +
1 REDIS POR EMPRESA
     +
1 BOT POR EMPRESA
```

Essa será a base para construir o MVP sem criar um monólito multi-tenant difícil de proteger.



---

# 68. Resumo executivo da arquitetura

```text
                    CODEBASE ÚNICO
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      EMPRESA A       EMPRESA B       EMPRESA C
          │              │              │
       Docker          Docker          Docker
          │              │              │
      FastAPI          FastAPI          FastAPI
      aiogram          aiogram          aiogram
      React            React            React
      PostgreSQL       PostgreSQL       PostgreSQL
      Redis            Redis            Redis
          │              │              │
       .env A           .env B          .env C
```

**Stack principal:**

```text
Python
FastAPI
aiogram
PostgreSQL
Redis
Worker
React + TypeScript
Docker
Nginx
GitHub Actions
Prometheus
Grafana
Sentry
```

**n8n:**

```text
OPTIONAL
```

Usado principalmente para integrações e automações externas, nunca como dependência do funcionamento principal do bot.

**Segurança:**

```text
ISOLAMENTO POR EMPRESA
+
SECRETS INDEPENDENTES
+
BANCO INDEPENDENTE
+
REDIS INDEPENDENTE
+
RBAC
+
2FA
+
AUDITORIA
+
RATE LIMITING
+
IDEMPOTÊNCIA
+
WEBHOOK SECURITY
+
BACKUPS
+
MONITORAMENTO
```

A primeira implementação deve priorizar **fundação, segurança e isolamento** antes de adicionar automações avançadas.
