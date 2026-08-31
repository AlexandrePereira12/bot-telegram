# Seeds — dados de demonstração

Conteúdo **fictício** para exercitar o funil inteiro antes de existir tráfego
real. Nada aqui é material de publicação, e nada aqui roda sozinho: seed é
sempre um comando explícito.

## Campanha Aviator (`campanha_aviator.py`)

```bash
docker compose exec -T api python -m seeds.campanha_aviator --campaign-id 1
```

Sem `--campaign-id`, procura a campanha chamada "Campanha de teste".

Popula uma campanha com o funil completo: seis etapas (`WELCOME`,
`QUALIFICATION`, `INFORMATION`, `AI_SUPPORT`, `HUMAN_SUPPORT`, `FOLLOWUP`) e sete opções de
qualificação — **seis direções informativas antes da única porta para o
atendimento humano**. Consentimento e age gate não entram: são globais por
decisão de compliance, e um seed que os sobrescrevesse por campanha quebraria a
auditoria do aceite.

### Por que essa variedade de opções

O teste precisa cobrir os caminhos que se comportam de forma diferente, não só
repetir o mesmo:

| Opção | O que exercita |
|---|---|
| `como_funciona`, `cash_out`, `modo_demo`, `pagamentos`, `jogo_responsavel` | resposta própria **com** imagem |
| `conta_documentos` | resposta própria **sem** imagem |
| `falar_atendente` | opção sem resposta: abre o atendimento por IA (`AI_SUPPORT`) ou, com a IA desligada, cai na mensagem da etapa `HUMAN_SUPPORT` |

Assim um único percurso passa por texto puro, texto com mídia, retorno ao menu
e transferência para pessoa — que são os quatro comportamentos que o funil tem.

### Compliance é verificada antes da escrita

Todo texto passa por `assert_compliant` — o mesmo validador da API — **antes**
de qualquer `INSERT`. Um texto reprovado derruba o seed inteiro em vez de deixar
a campanha metade nova e metade velha. É por isso que as respostas descrevem a
mecânica e o risco em vez de sugerir resultado: "o valor daquela entrada é
perdido" aparece mais de uma vez de propósito.

### Idempotente

Rodar duas vezes deixa o mesmo estado. O conteúdo anterior da campanha é
removido junto com a mídia que só ele referenciava — sem opção duplicada e sem
objeto órfão em `media_objects`.

## Imagens (`imagens/*.jpg`)

Sete telas de 1280×720 geradas por `gerar-imagens.mjs`, que renderiza HTML/SVG
no Chromium e tira a captura:

```bash
cd frontend && OUT=../backend/seeds/imagens node ../backend/seeds/gerar-imagens.mjs
# depois: ffmpeg -i entrada.png -q:v 4 saida.jpg
```

Sem arte externa e sem logotipo de terceiro: é material de teste, e precisa ser
reproduzível por quem clonar o repositório. Todas carregam "material fictício
para teste do funil" e o selo 18+.

JPEG e não PNG porque o conjunto cai de 2,4 MB para 500 KB — e agora a mídia
vive dentro do PostgreSQL, então o tamanho de cada arquivo é peso no banco e no
`pg_dump`, não bytes num volume que ninguém copia.
