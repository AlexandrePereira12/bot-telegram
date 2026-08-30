# Rotas da API

Prefixo `/api/v1` (exceto `health`). Cada rota passa por um schema explícito de
entrada e saída — nenhum modelo ORM é serializado direto, para não vazar coluna
interna (`password_hash`, `totp_secret`, `ip_hash`).

## `operators.py` — cadastro de usuários do painel

**Por que existe, se a CLI já cria operador.** O `python -m app.cli create-admin`
exige acesso ao servidor. Numa operação com time crescendo, cada usuário novo
virava chamado para quem tem shell. A rota resolve isso para todos os cadastros
*depois* do primeiro.

**Por que a CLI continua existindo.** A rota exige um ADMIN já autenticado. Numa
instalação nova não existe ADMIN algum, então o primeiro administrador só pode
vir da CLI. Não é redundância: é o único jeito de fechar o ciclo sem criar um
caminho de cadastro sem autenticação — que seria exatamente a porta que a rota
deveria proteger.

**Por que a senha é opcional.** Sem senha no corpo, o servidor gera uma
(`secrets.token_urlsafe(16)`) e a devolve **uma única vez** na resposta do
cadastro, igual ao que a CLI faz. Isso evita a senha fraca escolhida no calor do
cadastro. A senha nunca vai para a auditoria: o registro guarda `{email, role}`,
quem criou e o hash do IP — nunca o segredo.

**Por que ADMIN não ganha segredo de 2FA aqui.** Mesmo motivo do `create-admin`:
o segredo nasce no primeiro login do próprio dono, vira QR no navegador dele e
não circula por terminal, log ou histórico de quem cadastrou. Por isso a
listagem expõe `totp_pending` — é como quem administra sabe que o novo ADMIN
ainda não configurou o autenticador.

**Por que `OperatorAdminOut` é separado de `OperatorOut`.** `OperatorOut` é a
resposta de `/auth/me`; ampliá-lo mudaria um endpoint de sessão para atender uma
tela administrativa. São públicos diferentes, schemas diferentes.

**Por que a consulta filtra `tenant_id`.** O modelo é multi-tenant
(`TenantMixin`, `uq_operators_tenant_email`). Sem o filtro, a tela de
administração enumeraria operadores de outras instalações — a falha mais cara
possível justamente na tela que lista contas.

**Desativar e excluir não são a mesma coisa — e o painel não finge que são.**
Todas as chaves estrangeiras que apontam para `operators` são
`ON DELETE SET NULL`. Um `DELETE` passaria sem erro e, em silêncio, tiraria o
autor de linhas da auditoria (que é append-only), o remetente de mensagens já
enviadas e o responsável por atendimentos encerrados. Por isso:

- `DELETE` só é aceito enquanto o operador **não** tem histórico — nenhuma linha
  de auditoria como ator, nenhuma mensagem, nenhuma conversa atribuída ou
  encerrada por ele. É o caso do cadastro errado, corrigido no mesmo dia.
- Quem já trabalhou no sistema é **desativado** (`is_active=false`). O corte é
  imediato, porque a linha do operador é relida a cada requisição, e o rastro de
  quem fez o quê continua íntegro.

Quando a exclusão é recusada, o 409 diz exatamente isso — a mensagem é o que
ensina a diferença para quem administra.

**Dois guardas, em camadas diferentes.**

*Ação sobre si mesmo* (na rota): perfil, acesso e exclusão da própria conta são
recusados. Um administrador que se rebaixa perde o acesso na mesma requisição.
Editar o próprio nome continua liberado.

*Último administrador* (no serviço, `ensure_admin_remains`): nenhuma operação
pode deixar o tenant sem ADMIN ativo — isso trancaria a instalação, e só a CLI,
com acesso ao servidor, conseguiria destravá-la. Hoje, pela API, esse caso é
inalcançável: quem chama já é um ADMIN ativo, então a tentativa cairia antes no
guarda de ação sobre si mesmo. O guarda existe para o dia em que `admin:write`
for concedido a outro perfil, e é testado no serviço justamente por isso.

**O reset de 2FA é o mesmo da CLI.** `reset_totp` vive no `auth_service` e é
usado tanto por `python -m app.cli reset-2fa` quanto pela rota: uma lógica só,
para os dois caminhos não divergirem. O segredo antigo é descartado, nunca
reexibido, e o próximo login mostra um QR novo.
