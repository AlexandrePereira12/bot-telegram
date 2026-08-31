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
