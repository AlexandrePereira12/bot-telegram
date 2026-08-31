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
NEW → WELCOME → CONSENT → AGE_GATE → QUALIFICATION → INFORMATION ─────┐
                    │          │            │                         ├→ CONVERTED
                    │          │            └→ AI_SUPPORT → HUMAN_SUPPORT
                    └──────────┴────────────────→ EXIT (terminal)
```

`AI_SUPPORT` existe separado de `HUMAN_SUPPORT` para a métrica distinguir o que a IA resolveu do que
precisou de gente. Com o atendimento por IA desligado, o funil pula direto para `HUMAN_SUPPORT`.

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

### Atende com IA antes de ocupar uma pessoa

Quando o lead pede atendimento, quem responde primeiro é uma IA (OpenRouter, modelo configurável)
conversando pelo Telegram com o conteúdo cadastrado da campanha como base. A pessoa entra quando o
lead **insiste** em falar com gente — um botão "Falar com uma pessoa" acompanha toda resposta, e o
segundo pedido tira a IA de cena.

Três garantias valem mais que a resposta em si: a saída passa pela **mesma validação de compliance**
da API, então promessa de ganho não chega ao Telegram; **falha do provedor nunca prende o lead**
(timeout, cota estourada ou erro caem na fila humana, como antes); e a IA **não fala por cima do
operador** — a checagem de conversa atribuída vem antes de tudo no handler.

A chave de API é cadastrada em **Configurações** no painel (perfil ADMIN) e guardada **cifrada** no
banco — não em variável de ambiente. Cifrada, e não hasheada, porque o bot precisa dela em claro para
chamar o provedor; o que a tela exibe é uma máscara (`AIza••••••3f9K`), e ver a chave inteira exigiria
o banco e o `ENCRYPTION_KEY` do servidor ao mesmo tempo. Sem integração ativa, o atendimento por IA
não existe: o lead vai direto para a fila, como sempre foi.

Dois provedores aceitos — Google Gemini e OpenRouter — porque o formato da chamada muda entre eles. A
tela tem um botão de testar conexão, para chave errada aparecer ali e não quando um lead ficar sem
resposta.

### Passa a conversa para uma pessoa quando precisa

O operador assume a conversa e o bot silencia automaticamente. A resposta sai pelo painel — texto,
imagem, vídeo ou áudio gravado ali mesmo — e é entregue por um worker, então instabilidade do
Telegram não derruba a requisição.

A conversa aparece inteira no painel, incluindo o que o lead mandou: foto, vídeo e áudio são
baixados do Telegram no momento em que chegam e exibidos dentro da bolha. Anexo sem legenda também
entra — antes, foto sem texto não casava com nenhum handler e sumia sem virar registro.

Encerrar exige dizer **como terminou**: converteu ou não, com valor e observação opcionais, e sem
desfecho pré-marcado — a confirmação mostra o que será gravado antes de gravar. Dá para mandar uma
despedida junto, que fica registrada dentro do atendimento que ela encerrou. O atendimento sai da
fila e vai para o histórico. Se o lead voltar a escrever, começa um ciclo novo, com sua própria
conversa e seu próprio desfecho — sem repetir termos nem verificação de idade, e sem apagar a
conversão do ciclo anterior. Encerramento errado se corrige reabrindo o mesmo atendimento, sem
esperar o lead escrever.

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
| Banco | PostgreSQL 16 · SQLAlchemy 2 · Alembic (mídia inclusive, em `bytea`) |
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
├── models/        19 tabelas
├── services/      funil, tracking, conversão, conteúdo, atendimento, compliance
├── api/routes/    45 endpoints REST
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

**Excluir usuário é a exceção, desativar é a regra.** As chaves estrangeiras para
`operators` são `ON DELETE SET NULL`: apagar alguém que já trabalhou no sistema tiraria, em silêncio,
o autor de linhas da auditoria e o remetente de mensagens enviadas. Por isso o painel só exclui em
definitivo quem ainda não produziu histórico; o resto é desativado, o que corta o acesso na hora e
preserva o rastro. Nenhuma operação pode deixar a instalação sem administrador ativo, e ninguém
altera o próprio perfil ou acesso pelo painel.

**O cadastro de usuários pelo painel não elimina a CLI — depende dela.** A rota
exige um ADMIN autenticado, então o primeiro administrador de uma instalação continua vindo do
`create-admin`. Um caminho de cadastro sem autenticação seria justamente a porta que essa tela
deveria proteger. A senha pode ser gerada pelo servidor e aparece uma única vez na resposta; a
auditoria registra quem criou quem, com qual perfil — nunca a senha.

**O papel do operador é relido do banco a cada requisição.** O claim do JWT serve para a interface
decidir o que mostrar; ele não autoriza nada sozinho. Desativar um operador tem efeito imediato, sem
esperar token expirar.

**Toda a mídia vive no PostgreSQL, e nada é gravado em disco.** Imagem, vídeo e áudio são linhas de
`media_objects` (`bytea`), não arquivos num volume. O motivo é de operação, não de gosto: com o
arquivo fora do banco, restaurar o dump devolvia a conversa apontando para um arquivo que não existia
mais — buraco no histórico, sem erro em lugar nenhum. Agora `pg_dump` é o backup completo do
atendimento, e o par (mensagem, anexo) entra e sai na mesma transação.

**A mídia é servida por id de mensagem, não por id do arquivo.** A única porta é
`GET /conversations/{id}/messages/{id}/media`, autenticada e escopada por conversa: ninguém varre
`media_objects` por id sequencial, e a autorização sai de graça em vez de virar um servidor de
arquivos genérico. Como `<img src>` não manda header, o navegador busca por `fetch` e usa um blob
local — token em query string vazaria em log de proxy e histórico.

**O anexo do chat tem rota própria por causa da permissão.** `POST /content/media` exige
`campaigns:write`, que só ADMIN e MANAGER têm — ou seja, o clipe do chat respondia 403 justamente
para OPERATOR e SUPPORT, que são quem atende. Em vez de afrouxar a permissão do funil, o chat ganhou
`POST /conversations/{id}/media` sob `conversations:write`: quem anexa uma imagem numa conversa não
ganha com isso o direito de editar as mensagens do funil.

**Formato é decidido pelo conteúdo, e áudio é discriminado do vídeo.** MP4 e M4A compartilham o mesmo
`ftyp`; sem olhar o brand, todo áudio entraria como vídeo e sairia pelo `send_video`. Ogg só vira
mensagem de voz quando é Opus de verdade. Cada tipo tem seu método no Telegram, e tipo desconhecido
cai para texto em vez de ser mandado pelo método errado.

**Só o Nginx é publicado.** PostgreSQL e Redis vivem na rede interna. `/metrics` não é servido
publicamente — um allowlist por IP nessa camada seria inútil, porque atrás do Docker todo cliente
externo chega com o endereço da bridge. A documentação interativa desaparece sozinha em produção.

Além disso: Argon2 para senhas, HMAC-SHA256 com janela de timestamp nos webhooks, rate limiting em
duas camadas, auditoria append-only com IP em hash, e um formatter de log que redige campos sensíveis
antes de escrever.

---

## Como a qualidade é verificada

**191 testes** cobrindo o que quebraria em silêncio: age gate bloqueando reentrada, consentimento
versionado com revogação, idempotência de conversão, RBAC negando escrita ao perfil errado,
assinatura de webhook rejeitando replay e corpo adulterado, resolução de conteúdo por campanha,
o ciclo de encerrar e reabrir um atendimento, a rota de mídia negando anexo de outra conversa ou de
outro tenant, a detecção de formato separando M4A de MP4, a conversão de uma gravação de navegador
em OGG/Opus com o ffmpeg de verdade, e o atendimento por IA — que não fala por cima do operador, não
deixa promessa de ganho sair e manda o lead para a fila quando o provedor falha.

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
