# Serviços — decisões do atendimento e da mídia

Este arquivo registra **por que** as coisas estão como estão. O que elas fazem está no código e nas
docstrings; o que se perde com o tempo é o motivo.

## Mídia (`media_service.py`)

**Os arquivos vivem no PostgreSQL, não em volume.** Imagem, vídeo e áudio são linhas de
`media_objects`, com os bytes na coluna `content`. O motivo é de operação: com o arquivo fora do
banco, restaurar o dump devolvia a conversa com o caminho de um arquivo que não existia mais — buraco
no histórico, sem erro em lugar nenhum, e ninguém percebe até alguém abrir um atendimento antigo.
Agora `pg_dump` é o backup completo, e o processo não escreve nada em disco.

**`bytea`, não large object.** Com teto de 20MB por arquivo, o TOAST guarda o conteúdo fora da linha
e comprime sozinho. `lo_*` exigiria `vacuumlo` e um caminho próprio de backup, sem ganho nessa faixa
de tamanho.

**20MB é o limite do Telegram, não um número escolhido aqui.** É o teto de download de arquivo por
bot: acima disso, guardaríamos no banco algo que nunca conseguiria sair.

**O tipo vem do conteúdo, nunca da extensão.** Renomear `.exe` para `.jpg` não passa pela detecção
por assinatura. A validação vale igual para o que o painel envia e para o que o lead manda pelo
Telegram — arquivo de fora é arquivo de fora.

**M4A e MP4 têm o mesmo `ftyp` no offset 4.** O que separa os dois é o brand no offset 8
(`M4A `, `M4B `, `M4P ` são áudio). Sem essa checagem, todo áudio em container ISO-BMFF entraria como
vídeo e sairia pelo `send_video`, que o Telegram recusa ou entrega como coisa errada. O mesmo
raciocínio vale para Ogg: só é mensagem de voz quando tem `OpusHead`; Ogg/Vorbis vai como arquivo de
áudio.

**`VOICE` e `AUDIO` são tipos diferentes de propósito.** O Telegram trata voz (`sendVoice`, OGG/Opus,
bolha com forma de onda) e áudio (`sendAudio`, arquivo com título e duração) como coisas distintas.
Colapsar os dois num tipo só forçaria o envio pelo método errado em metade dos casos.

**A extensão é guardada na linha.** Ela deixou de existir como nome de arquivo, mas `sendVoice` e
`sendAudio` decidem o tipo pelo nome que sobe — por isso `MediaObject.filename()`.

**A conversão de voz usa ffmpeg, e por isso ele está na imagem.** O `MediaRecorder` do navegador
entrega WebM/Opus no Chrome e MP4/AAC no Safari; o `sendVoice` só aceita OGG/Opus. Recodificar no
servidor é o que permite gravar direto no painel sem depender do navegador de quem atende. Mono a
32kbps: é voz, e assim o limite de 20MB nunca é alcançado na prática.

**O arquivo temporário do ffmpeg é buffer, não armazenamento.** `pipe:` não serve para o MP4 do
Safari, cujo índice fica no fim e exige seek; o arquivo vive dentro de um `TemporaryDirectory` e some
ao fim da chamada. O que persiste vai para o banco.

**`save()` não faz commit.** Quem chama decide a transação — e é isso que garante que o anexo e a
mensagem entrem juntos ou não entrem. Rollback não deixa mais objeto órfão.

**`load()` filtra por tenant.** Id de outra empresa devolve `None`, não a linha. Como o único
endereço público é por id de mensagem (`/conversations/{id}/messages/{id}/media`), ninguém varre
`media_objects` por id sequencial.

**Anexo que sobe e não é enviado tem que sair.** O upload grava antes de existir qualquer mensagem,
então trocar o anexo, remover ou descartar uma gravação deixaria linha órfã — e gravação de voz
multiplica isso, porque cada tentativa descartada é um objeto. Daí o
`DELETE /conversations/{id}/media`, que só apaga o que **nenhuma** mensagem referencia: remover a
mídia de uma mensagem já entregue deixaria a conversa com um buraco no histórico.

**Áudio no funil vai sem conversão.** Só o chat passa pelo `transcode_voice`; um `.ogg` Opus subido
pelo painel de conteúdo é enviado como voz do jeito que veio. Se o arquivo não servir, o `_deliver`
cai para texto e registra `MEDIA_SEND_FAILED` — degradação com log, o mesmo comportamento que o
projeto já escolheu para mídia problemática.

**A migration 0007 aborta em vez de perder arquivo.** Ela importa o que estava no volume; se alguma
linha apontar para arquivo ilegível, o upgrade falha. Gravar `NULL` e seguir seria exatamente o
sumiço silencioso que a mudança quer eliminar. Consequência de deploy: o volume legado precisa
continuar montado no momento do upgrade, e só pode sair do compose depois que a 0007 tiver rodado em
todas as instalações.

## Atendimento por IA (`ai_service.py`)

**A IA entra no lugar da fila, não antes do operador.** Escolher "falar com atendente" leva ao estado
`AI_SUPPORT`, onde o modelo do provedor configurado conversa normalmente. A pessoa assume quando o
lead insiste em falar com gente.

**O interruptor é a integração cadastrada, não uma variável de ambiente.** Sem linha ativa em
`ai_integrations`, o atendimento por IA não existe para a instalação e o lead vai direto para a fila —
o comportamento de sempre. `disponivel()` consulta o banco a cada mensagem em vez de cachear: cache
aqui significaria a IA continuar respondendo depois de alguém desligar no painel, e o interruptor
precisa ser imediato.

**A chave de API é cifrada, não hasheada — e a diferença não é preciosismo.** Hash resolveria
"ninguém lê", mas também impediria o bot de usar a chave: ele precisa dela em claro no momento da
chamada. Então ela é cifrada com material derivado do `ENCRYPTION_KEY` (Fernet sobre SHA-256 do
segredo do ambiente), e o que a tela mostra é uma máscara montada a partir de `api_key_hint`, que
guarda só as pontas. Ver a chave inteira exige o banco **e** o segredo do servidor.

**A chave mora no banco, e não no `.env`.** Trocar de chave é operação de quem administra, não de
quem tem acesso ao servidor — e não deveria exigir deploy. Consequência assumida: o segredo entra no
`pg_dump`, cifrado; um dump vazado sem o `ENCRYPTION_KEY` não entrega a chave.

**Dois provedores porque o formato da chamada muda.** Gemini usa `contents`/`systemInstruction` com a
chave em header `x-goog-api-key`; OpenRouter segue chat completions com `Authorization: Bearer`. A
chave vai em header nos dois, nunca em query string — URL com segredo vaza em log de proxy e em
histórico de navegador. A diferença fica isolada em duas funções; o resto do serviço não sabe qual
provedor está ativo.

**O teste de conexão existe para o erro aparecer no painel.** Sem ele, chave errada só se manifesta
quando um lead fica sem resposta. O resultado (`last_checked_at`, `last_error`) fica na linha, então a
tela mostra o último teste sem repetir a chamada — e sem gastar cota — a cada carregamento.

**A ordem das checagens em `on_message` é regra de negócio.** `is_under_human_support` vem antes de
tudo: com o gancho da IA acima daquele gate, o modelo responderia por cima do operador que já assumiu
a conversa — sem erro, sem log, e o lead recebendo duas vozes. É a única linha do handler cuja
posição tem efeito silencioso e caro, e existe teste fixando isso.

**A saída passa pela mesma validação de compliance da escrita.** Texto com promessa de ganho não
chega ao Telegram. Num funil de apostas, soltar um gerador de texto sem essa checagem seria trocar a
rede de proteção por sorte. Violação **não escala** — o lead recebe a mensagem de indisponibilidade e
o termo fica no log, que é onde se decide se o prompt precisa mudar. Escalar por violação seria punir
o lead por um erro nosso, e ele não teria como entender o motivo.

**Insistência tem evento próprio (`AI_HANDOFF_REQUESTED`), separado de `HUMAN_SUPPORT_REQUESTED`.**
Escolher "falar com atendente" no menu é como se chega ao atendimento — contar isso como insistência
faria a IA sair de cena antes de responder uma única vez. Só pedidos feitos **dentro** do atendimento
contam, e o limiar é `AI_ESCALATE_AFTER_REQUESTS` (2 por padrão).

**Quem decide sair da IA é o lead, não o modelo.** A detecção é por frase (`PEDIDOS_DE_HUMANO`), no
nosso código: um gate que dependesse do julgamento do modelo estaria pedindo justamente à parte que o
lead quer abandonar que reconheça a própria dispensa. O botão "Falar com uma pessoa" acompanha toda
resposta, com callback próprio (`humano:pedir`) — reusar `interest:<key>` não funcionaria, porque o
handler de qualificação descarta clique fora de `QUALIFICATION`/`INFORMATION` e o botão ficaria mudo.

**Falha nunca prende o lead.** Timeout, 429 (comum em modelo gratuito) ou erro de rede caem no caminho
de sempre: aviso curto e fila humana. O serviço nunca deixa exceção subir para o handler.

**A base de conhecimento é o conteúdo cadastrado — e não só as respostas.** O prompt recebe a
campanha de onde o lead veio, a mensagem de boas-vindas (onde o produto é apresentado), o menu
completo e as respostas de cada opção. A primeira versão mandava só as respostas soltas: o modelo não
sabia o nome da campanha, não tinha a apresentação e não conhecia o menu — então não conseguia dizer
"posso te explicar o cash out". Editar uma etapa ou opção no painel muda o que a IA responde, sem
tocar em código nem em prompt. Fora disso o modelo usa o conhecimento geral dele sobre o jogo, o que
foi decisão explícita de quem pediu a feature.

**O raciocínio do Gemini `flash` é desligado, e isso não é economia.** O `maxOutputTokens` do Gemini
cobre raciocínio **e** texto no mesmo teto. Medindo a chamada real: 476 tokens gastos pensando para
13 de resposta. Com o teto em 500, a resposta chegava vazia, o serviço tratava como falha e o lead ia
para a fila sem entender por quê — o sintoma era "a IA não respondeu nada". `thinkingBudget: 0` só é
enviado para modelos `flash`; no `pro` o mínimo é 128 e zero seria 400.

**Falha de geração carrega o diagnóstico.** `ValueError` sozinho não diz se foi filtro de segurança,
teto de tokens ou raciocínio comendo o orçamento. A mensagem leva `finishReason`, tokens de
raciocínio e de saída, e isso vai para o log e para o metadata do evento `AI_FAILED` — foi assim que
o caso acima virou diagnóstico em vez de suposição.

**A IA não finge ser humana.** O tom é natural e ela não se anuncia a cada mensagem, mas perguntada
diretamente, responde a verdade. A regra está no system prompt, não no código: é regra de conversa.

**Dado sensível não passa pela IA por instrução do prompt.** O material da campanha fala de CPF,
documento e selfie; o prompt proíbe pedir esses dados e manda oferecer transferência para uma pessoa
quando o assunto for cadastro, saque travado ou conta bloqueada. Vale saber que endpoints gratuitos
de LLM podem rotear para provedores que usam os dados da requisição — por isso a instrução existe, e
por isso trocar de modelo é decisão de configuração, não de código.

**`httpx`, sem SDK novo.** Já é dependência do projeto (o mesmo cliente do `notify_external`), e a API
do OpenRouter é compatível com o formato de chat completions. O ID do modelo fica em variável de
ambiente porque os modelos gratuitos entram e saem do catálogo — fixá-lo no código faria a feature
quebrar sozinha quando o provedor aposentasse o modelo.

## Atendimento (`conversation_service.py`)

**`ConversationNotFound` existe para a API poder responder 404.** Antes, "conversa inexistente" e
"operação não cabe neste estado" chegavam como a mesma exceção, e cada rota escolhia um código: o
mesmo erro virava 404 no `release` e 409 no `close`.

**A despedida é registrada antes da mudança de status.** Assim ela aparece no histórico dentro do
atendimento que encerrou, e não solta depois dele. O envio fica com o worker, como qualquer outra
resposta do operador — e só é enfileirado depois do commit: mensagem entregue ao lead sem o
encerramento gravado seria o pior dos dois mundos.

**Reabrir é desfazer o encerramento, não apagar o histórico.** A conversa volta para a fila como
`OPEN` e sem atribuição (quem reabriu não necessariamente vai atender), o desfecho volta a ser NULL,
e as mensagens continuam. Uma conversão já registrada **não** é desfeita: o `external_id` continua
`manual:<id da conversa>`, então encerrar de novo como convertido cai na mesma constraint única e
não gera segunda conversão. Reabrir não pode virar caminho para contar a mesma venda duas vezes.

**O funil só reabre quando o lead permite.** Quem foi reprovado no age gate ou nunca aceitou os
termos segue de fora — nesse caso a conversa reabre e o funil não, e o motivo fica no log. O age gate
é a regra com exposição legal do projeto; nenhuma operação de conveniência passa por cima dele.

## Mensagem recebida com anexo (`app/bot/replies.py`)

O arquivo é baixado no momento em que chega porque o `file_id` do Telegram expira e exige o token do
bot — o navegador de quem atende nunca alcançaria a mídia direto. O objeto de mídia e a mensagem são
gravados na mesma sessão, então rollback não deixa órfão. Falha no download não derruba o registro:
a linha entra sem anexo e o motivo fica no log. Perder o arquivo é melhor que perder a conversa.
