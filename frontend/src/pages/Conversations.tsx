import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import {
  ConfirmDialog,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  StatusBadge,
  datetime,
} from '../components'
import {
  api,
  discardConversationMedia,
  fetchMessageMedia,
  uploadConversationMedia,
} from '../services/api'
import type {
  Conversation,
  ConversationDetail,
  ConversationOutcome,
  MediaType,
  Message,
  Operator,
} from '../types'

/** Anexo pronto para enviar. `preview` é um object URL local, só para o
 *  operador conferir antes de mandar — some ao enviar ou remover. */
interface Anexo {
  id: number
  type: MediaType
  preview: string | null
}

/** Motivos que se repetem no dia a dia, por desfecho. Clicar preenche o campo,
 *  que continua livre: a lista existe para padronizar o comum, não para
 *  limitar o que dá para escrever. */
const MOTIVOS: Record<ConversationOutcome, string[]> = {
  CONVERTED: ['fechou na hora', 'já era cliente', 'renovou o plano'],
  NOT_CONVERTED: [
    'fora do perfil',
    'sem resposta',
    'achou caro',
    'contato duplicado',
    'só queria informação',
  ],
}

const ROTULO_MIDIA: Record<MediaType, string> = {
  photo: 'imagem',
  video: 'vídeo',
  voice: 'áudio gravado',
  audio: 'áudio',
}

function OutcomeBadge({ outcome }: { outcome: ConversationOutcome | null }) {
  if (!outcome) return null
  return (
    <span className={`badge ${outcome === 'CONVERTED' ? 'ok' : 'danger'}`}>
      {outcome === 'CONVERTED' ? 'deu certo' : 'não converteu'}
    </span>
  )
}

/**
 * Anexo de uma mensagem dentro da bolha do chat.
 *
 * A rota da mídia é autenticada e `<img src>` não manda o header
 * Authorization — por isso o arquivo vem por fetch e vira object URL, que é
 * revogado ao desmontar para o blob não ficar preso na memória da aba.
 */
function AnexoMensagem({
  conversationId,
  message,
}: {
  conversationId: number
  message: Message
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [erro, setErro] = useState(false)

  useEffect(() => {
    let ativo = true
    let criado: string | null = null

    fetchMessageMedia(conversationId, message.id)
      .then((objectUrl) => {
        criado = objectUrl
        if (ativo) setUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl)
      })
      .catch(() => {
        if (ativo) setErro(true)
      })

    return () => {
      ativo = false
      if (criado) URL.revokeObjectURL(criado)
    }
  }, [conversationId, message.id])

  const rotulo = message.media_type ? ROTULO_MIDIA[message.media_type] : 'anexo'

  if (erro) {
    return <span className="muted anexo-aviso">{rotulo} indisponível</span>
  }
  if (!url) {
    return <span className="muted anexo-aviso">carregando {rotulo}…</span>
  }
  if (message.media_type === 'photo') {
    return <img className="anexo-midia" src={url} alt={`${rotulo} da conversa`} />
  }
  if (message.media_type === 'video') {
    return <video className="anexo-midia" src={url} controls />
  }
  return <audio className="anexo-audio" src={url} controls />
}

/**
 * Gravação de áudio no próprio painel.
 *
 * O navegador entrega WebM/Opus (Chrome) ou MP4/AAC (Safari); a conversão
 * para OGG/Opus, que é o que o Telegram aceita como mensagem de voz,
 * acontece no servidor. Aqui só se grava e se envia o arquivo cru.
 */
function Gravador({
  disabled,
  enviando,
  onGravado,
}: {
  disabled: boolean
  enviando: boolean
  onGravado: (file: File) => void
}) {
  const [gravando, setGravando] = useState(false)
  const [segundos, setSegundos] = useState(0)
  const [erro, setErro] = useState<string | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const pedacos = useRef<Blob[]>([])

  // Navegador sem MediaRecorder (ou página sem HTTPS, onde getUserMedia não
  // existe): o botão simplesmente não aparece, em vez de falhar ao clicar.
  const suportado =
    typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  useEffect(() => {
    if (!gravando) return
    const timer = window.setInterval(() => setSegundos((s) => s + 1), 1000)
    return () => window.clearInterval(timer)
  }, [gravando])

  useEffect(() => {
    // Soltar o microfone se a tela sair no meio da gravação — sem isso o
    // indicador do navegador fica aceso depois de trocar de página.
    return () => {
      recorder.current?.stream.getTracks().forEach((t) => t.stop())
    }
  }, [])

  if (!suportado) return null

  const iniciar = async () => {
    setErro(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((m) =>
        MediaRecorder.isTypeSupported(m),
      )
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      pedacos.current = []
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) pedacos.current.push(e.data)
      }
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(pedacos.current, { type: rec.mimeType || 'audio/webm' })
        if (blob.size > 0) onGravado(new File([blob], 'gravacao', { type: blob.type }))
      }
      recorder.current = rec
      rec.start()
      setSegundos(0)
      setGravando(true)
    } catch {
      setErro('não foi possível acessar o microfone — confira a permissão do navegador')
    }
  }

  const parar = () => {
    recorder.current?.stop()
    recorder.current = null
    setGravando(false)
  }

  const cancelar = () => {
    const rec = recorder.current
    if (rec) {
      rec.onstop = null
      rec.stop()
      rec.stream.getTracks().forEach((t) => t.stop())
    }
    recorder.current = null
    setGravando(false)
  }

  if (gravando) {
    return (
      <span className="gravador">
        <span className="gravando-pulso" aria-hidden="true" />
        <span className="gravando-tempo">
          {String(Math.floor(segundos / 60)).padStart(2, '0')}:
          {String(segundos % 60).padStart(2, '0')}
        </span>
        <button type="button" onClick={parar} title="parar e anexar o áudio">
          parar
        </button>
        <button type="button" className="secondary" onClick={cancelar}>
          descartar
        </button>
      </span>
    )
  }

  return (
    <>
      <button
        type="button"
        className="secondary"
        onClick={iniciar}
        disabled={disabled || enviando}
        title="gravar áudio"
      >
        {enviando ? '…' : '🎤'}
      </button>
      {erro && (
        <span className="muted" style={{ fontSize: 11 }}>
          {erro}
        </span>
      )}
    </>
  )
}

export default function Conversations() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<number | null>(null)
  const [reply, setReply] = useState('')
  const [anexo, setAnexo] = useState<Anexo | null>(null)
  const [encerrando, setEncerrando] = useState(false)
  const [reabrindo, setReabrindo] = useState(false)
  // Encerrados saem da fila e ficam no histórico, que abre sob demanda.
  const [verHistorico, setVerHistorico] = useState(false)

  /** Some com o anexo da tela. Usado depois do envio, quando o arquivo já
   *  pertence a uma mensagem e não deve ser apagado do volume. */
  const limparAnexo = () => {
    setAnexo((atual) => {
      if (atual?.preview) URL.revokeObjectURL(atual.preview)
      return null
    })
  }

  /** Descarta um anexo que subiu e não foi enviado — sem isso ele fica no
   *  volume do servidor sem nenhuma mensagem apontando para ele. */
  const descartarAnexo = (alvo: Anexo | null) => {
    if (!alvo || selected === null) return
    discardConversationMedia(selected, alvo.id).catch(() => {
      /* já enviado ou já removido: nada a fazer na tela */
    })
  }

  const me = useQuery({ queryKey: ['me'], queryFn: () => api<Operator>('/auth/me') })

  const fila = useQuery({
    queryKey: ['conversations', 'fila'],
    queryFn: () => api<Conversation[]>('/conversations'),
    refetchInterval: 15_000,
  })
  const historico = useQuery({
    queryKey: ['conversations', 'historico'],
    queryFn: () => api<Conversation[]>('/conversations?status_filter=CLOSED'),
    enabled: verHistorico,
  })

  const detail = useQuery({
    queryKey: ['conversation', selected],
    queryFn: () => api<ConversationDetail>(`/conversations/${selected}`),
    enabled: selected !== null,
    refetchInterval: 10_000,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['conversations'] })
    queryClient.invalidateQueries({ queryKey: ['conversation', selected] })
  }

  const assign = useMutation({
    mutationFn: (id: number) =>
      api<Conversation>(`/conversations/${id}/assign`, { method: 'POST' }),
    onSuccess: invalidate,
  })

  const release = useMutation({
    mutationFn: (id: number) =>
      api<Conversation>(`/conversations/${id}/release`, { method: 'POST' }),
    onSuccess: invalidate,
  })

  const close = useMutation({
    mutationFn: (payload: {
      id: number
      outcome: ConversationOutcome
      reason: string
      value: string
      farewell: string
    }) =>
      api<Conversation>(`/conversations/${payload.id}/close`, {
        method: 'POST',
        body: JSON.stringify({
          outcome: payload.outcome,
          reason: payload.reason || null,
          value: payload.value ? Number(payload.value) : null,
          currency: payload.value ? 'BRL' : null,
          farewell: payload.farewell || null,
        }),
      }),
    // A conversa continua na tela, agora em somente leitura: fechar o painel
    // aqui escondia justamente o desfecho que o operador acabou de gravar.
    onSuccess: () => {
      setEncerrando(false)
      invalidate()
    },
  })

  const reopen = useMutation({
    mutationFn: (id: number) =>
      api<Conversation>(`/conversations/${id}/reopen`, { method: 'POST' }),
    onSuccess: () => {
      setReabrindo(false)
      invalidate()
    },
  })

  const send = useMutation({
    mutationFn: (id: number) =>
      api(`/conversations/${id}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          content: reply,
          media_id: anexo?.id ?? null,
          media_type: anexo?.type ?? null,
        }),
      }),
    onSuccess: () => {
      setReply('')
      limparAnexo()
      invalidate()
    },
  })

  const enviarAnexo = useMutation({
    mutationFn: ({ file, kind }: { file: File; kind?: 'voice' }) =>
      uploadConversationMedia(selected!, file, kind).then((r) => ({
        ...r,
        preview: URL.createObjectURL(file),
      })),
    onSuccess: (r) => {
      setAnexo((anterior) => {
        // Trocar de anexo sem enviar o primeiro deixaria o arquivo antigo
        // órfão no volume.
        descartarAnexo(anterior)
        if (anterior?.preview) URL.revokeObjectURL(anterior.preview)
        return { id: r.media_id, type: r.media_type, preview: r.preview }
      })
    },
  })

  // Encerradas não aparecem na fila — só no histórico.
  const abertas = (fila.data ?? []).filter((c) => c.status !== 'CLOSED')
  const aberta = detail.data && detail.data.status !== 'CLOSED'
  const minha = detail.data?.assigned_to === me.data?.id

  return (
    <>
      <h1>Conversas</h1>
      <p className="page-sub">
        Enquanto a conversa estiver atribuída, o bot não responde automaticamente
        aquele usuário.
      </p>

      <Panel title={`Fila de atendimento (${abertas.length})`}>
        {fila.isLoading && <Loading />}
        {fila.isError && <ErrorBox error={fila.error} />}
        {!fila.isLoading && abertas.length === 0 && (
          <Empty text="nenhum atendimento em aberto" />
        )}
        {abertas.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Status</th>
                <th>Atribuída a</th>
                <th>Início</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {abertas.map((c) => (
                <tr key={c.id}>
                  <td>#{c.id}</td>
                  <td>
                    <StatusBadge status={c.status} />
                  </td>
                  <td>
                    {c.assigned_to
                      ? c.assigned_to === me.data?.id
                        ? 'você'
                        : `operador ${c.assigned_to}`
                      : '—'}
                  </td>
                  <td className="muted">{datetime(c.started_at)}</td>
                  <td>
                    <button
                      className="secondary"
                      onClick={() => setSelected(selected === c.id ? null : c.id)}
                    >
                      {selected === c.id ? 'fechar' : 'abrir'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="Histórico de atendimentos">
        {!verHistorico ? (
          <button className="secondary" onClick={() => setVerHistorico(true)}>
            Ver atendimentos encerrados
          </button>
        ) : (
          <>
            {historico.isLoading && <Loading />}
            {historico.data?.length === 0 && <Empty text="nenhum atendimento encerrado" />}
            {historico.data && historico.data.length > 0 && (
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Resultado</th>
                    <th>Observação</th>
                    <th>Encerrado em</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {historico.data.map((c) => (
                    <tr key={c.id}>
                      <td>#{c.id}</td>
                      <td>
                        {c.outcome ? (
                          <OutcomeBadge outcome={c.outcome} />
                        ) : (
                          <span className="muted">sem resultado informado</span>
                        )}
                      </td>
                      <td className="muted">{c.outcome_reason ?? '—'}</td>
                      <td className="muted">{datetime(c.ended_at)}</td>
                      <td>
                        <button
                          className="secondary"
                          onClick={() => setSelected(selected === c.id ? null : c.id)}
                        >
                          {selected === c.id ? 'fechar' : 'ver'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </Panel>

      {selected !== null && detail.data && (
        <Panel title={`Conversa #${detail.data.id}`}>
          <div className="toolbar">
            {detail.data.lead_id && (
              <Link className="btn secondary" to={`/leads/${detail.data.lead_id}`}>
                ver lead #{detail.data.lead_id}
              </Link>
            )}

            {aberta && !detail.data.assigned_to && (
              <button
                onClick={() => assign.mutate(detail.data!.id)}
                disabled={assign.isPending}
              >
                Assumir atendimento
              </button>
            )}

            {aberta && minha && (
              <button className="secondary" onClick={() => release.mutate(detail.data!.id)}>
                Devolver para automação
              </button>
            )}

            {/* Encerrar não exige ter assumido: dá para fechar um atendimento
                que ninguém pegou (lead sumiu, contato duplicado). */}
            {aberta && (
              <button onClick={() => setEncerrando((v) => !v)}>
                {encerrando ? 'Cancelar' : 'Encerrar atendimento'}
              </button>
            )}

            {!aberta && (
              <>
                <span className="badge">encerrado</span>
                <OutcomeBadge outcome={detail.data.outcome} />
                {detail.data.outcome_reason && (
                  <span className="muted">{detail.data.outcome_reason}</span>
                )}
                <button className="secondary" onClick={() => setReabrindo(true)}>
                  Reabrir atendimento
                </button>
              </>
            )}
          </div>

          {assign.isError && <ErrorBox error={assign.error} />}
          {reopen.isError && <ErrorBox error={reopen.error} />}

          {encerrando && aberta && (
            <CloseForm
              onClose={(outcome, reason, value, farewell) =>
                close.mutate({ id: detail.data!.id, outcome, reason, value, farewell })
              }
              busy={close.isPending}
              error={close.error}
            />
          )}

          <ConfirmDialog
            open={reabrindo}
            title={`Reabrir atendimento #${detail.data.id}`}
            confirmLabel="Reabrir"
            busy={reopen.isPending}
            onConfirm={() => reopen.mutate(detail.data!.id)}
            onClose={() => setReabrindo(false)}
          >
            A conversa volta para a fila sem atribuição e o resultado registrado é
            apagado. As mensagens continuam no histórico, e uma conversão já
            contabilizada não é desfeita — encerrar de novo como convertido não
            gera outra.
          </ConfirmDialog>

          <div className="chat">
            {detail.data.messages.length === 0 && <Empty text="sem mensagens" />}
            {detail.data.messages.map((m) => (
              <div className={`bubble ${m.sender_type}`} key={m.id}>
                {m.media_type && (
                  <AnexoMensagem conversationId={detail.data!.id} message={m} />
                )}
                {m.content}
                <span className="meta">
                  {m.sender_type} · {datetime(m.created_at)}
                </span>
              </div>
            ))}
          </div>

          {aberta ? (
            <>
              {anexo && (
                <div className="anexo-pendente">
                  <span className="badge">{ROTULO_MIDIA[anexo.type]}</span>
                  {anexo.preview && anexo.type === 'photo' && (
                    <img className="anexo-preview" src={anexo.preview} alt="anexo" />
                  )}
                  {anexo.preview && anexo.type !== 'photo' && anexo.type !== 'video' && (
                    <audio className="anexo-audio" src={anexo.preview} controls />
                  )}
                  <button
                    className="secondary"
                    style={{ padding: '2px 8px', fontSize: 11 }}
                    onClick={() => {
                      descartarAnexo(anexo)
                      limparAnexo()
                    }}
                  >
                    remover
                  </button>
                </div>
              )}

              <form
                style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}
                onSubmit={(e) => {
                  e.preventDefault()
                  send.mutate(detail.data!.id)
                }}
              >
                <input
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder={
                    minha
                      ? anexo
                        ? 'legenda (opcional)'
                        : 'responder…'
                      : 'assuma a conversa para poder responder'
                  }
                  disabled={!minha}
                />
                <label
                  className="btn secondary"
                  style={{
                    cursor: minha ? 'pointer' : 'not-allowed',
                    opacity: minha ? 1 : 0.5,
                    whiteSpace: 'nowrap',
                  }}
                  title="anexar imagem, vídeo ou áudio"
                >
                  {enviarAnexo.isPending ? '…' : '📎'}
                  <input
                    type="file"
                    accept="image/*,video/*,audio/*"
                    style={{ display: 'none' }}
                    disabled={!minha}
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) enviarAnexo.mutate({ file: f })
                      e.target.value = ''
                    }}
                  />
                </label>
                <Gravador
                  disabled={!minha}
                  enviando={enviarAnexo.isPending}
                  onGravado={(file) => enviarAnexo.mutate({ file, kind: 'voice' })}
                />
                <button
                  type="submit"
                  disabled={!minha || (!reply && !anexo) || send.isPending}
                >
                  Enviar
                </button>
              </form>
              {send.isError && <ErrorBox error={send.error} />}
              {enviarAnexo.isError && <ErrorBox error={enviarAnexo.error} />}
            </>
          ) : (
            <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
              Atendimento encerrado — somente leitura. Se o lead escrever de novo,
              um atendimento novo aparece na fila.
            </p>
          )}
        </Panel>
      )}
    </>
  )
}

/**
 * Formulário de encerramento.
 *
 * O desfecho começa sem escolha: com "converteu" pré-marcado, um clique
 * distraído em confirmar registrava conversão — e conversão inventada é o que
 * estraga CPA e taxa de conversão. Valor, motivo e despedida são opcionais, e
 * a confirmação mostra o que será gravado antes de gravar.
 */
function CloseForm({
  onClose,
  busy,
  error,
}: {
  onClose: (
    outcome: ConversationOutcome,
    reason: string,
    value: string,
    farewell: string,
  ) => void
  busy: boolean
  error: unknown
}) {
  const [outcome, setOutcome] = useState<ConversationOutcome | null>(null)
  const [reason, setReason] = useState('')
  const [value, setValue] = useState('')
  const [farewell, setFarewell] = useState('')
  const [confirmando, setConfirmando] = useState(false)

  return (
    <div className="close-form">
      <h2 style={{ fontSize: 13, marginTop: 0 }}>Como terminou o atendimento?</h2>

      <div className="toolbar" style={{ marginBottom: 10 }}>
        <button
          className={outcome === 'CONVERTED' ? '' : 'secondary'}
          onClick={() => {
            setOutcome('CONVERTED')
            setReason('')
          }}
          type="button"
        >
          Deu certo (converteu)
        </button>
        <button
          className={outcome === 'NOT_CONVERTED' ? '' : 'secondary'}
          onClick={() => {
            setOutcome('NOT_CONVERTED')
            setValue('')
            setReason('')
          }}
          type="button"
        >
          Não converteu
        </button>
      </div>

      {outcome === null && (
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          Escolha o desfecho para continuar — é ele que entra nas métricas de
          conversão.
        </p>
      )}

      {outcome === 'CONVERTED' && (
        <div className="field">
          <label>Valor da conversão (opcional)</label>
          <input
            inputMode="decimal"
            value={value}
            placeholder="250.00"
            onChange={(e) => setValue(e.target.value.replace(/[^\d.]/g, ''))}
          />
        </div>
      )}

      {outcome !== null && (
        <>
          <div className="field">
            <label>Observação (opcional)</label>
            <div className="motivos">
              {MOTIVOS[outcome].map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`motivo ${reason === m ? 'ativo' : ''}`}
                  onClick={() => setReason(reason === m ? '' : m)}
                >
                  {m}
                </button>
              ))}
            </div>
            <input
              value={reason}
              maxLength={255}
              placeholder={
                outcome === 'CONVERTED' ? 'fechou o plano anual' : 'fora do perfil'
              }
              onChange={(e) => setReason(e.target.value)}
            />
          </div>

          <div className="field">
            <label>Mensagem de despedida (opcional)</label>
            <textarea
              value={farewell}
              maxLength={4000}
              rows={2}
              placeholder="Obrigado pelo contato! Qualquer coisa, é só chamar."
              onChange={(e) => setFarewell(e.target.value)}
            />
            <small className="muted" style={{ fontSize: 11 }}>
              Enviada ao lead no Telegram antes de fechar, e registrada nesta
              conversa. Em branco, nada é enviado.
            </small>
          </div>
        </>
      )}

      {error != null && <ErrorBox error={error} />}

      <button onClick={() => setConfirmando(true)} disabled={busy || outcome === null}>
        Encerrar atendimento
      </button>
      <small className="muted" style={{ fontSize: 11, display: 'block', marginTop: 8 }}>
        Encerrado, sai da fila e vai para o histórico. Se o lead voltar a escrever,
        inicia um atendimento novo — e dá para reabrir este mesmo pelo histórico.
      </small>

      <ConfirmDialog
        open={confirmando}
        title="Confirmar encerramento"
        confirmLabel="Encerrar"
        busy={busy}
        onConfirm={() => {
          setConfirmando(false)
          if (outcome) onClose(outcome, reason, value, farewell)
        }}
        onClose={() => setConfirmando(false)}
      >
        <ul className="resumo-encerramento">
          <li>
            Resultado: <strong>{outcome === 'CONVERTED' ? 'converteu' : 'não converteu'}</strong>
            {outcome === 'CONVERTED' && ' — a conversão entra nas métricas'}
          </li>
          {outcome === 'CONVERTED' && <li>Valor: {value ? `R$ ${value}` : 'não informado'}</li>}
          <li>Observação: {reason || 'nenhuma'}</li>
          <li>
            Despedida:{' '}
            {farewell.trim() ? 'será enviada ao lead' : 'nenhuma mensagem será enviada'}
          </li>
        </ul>
      </ConfirmDialog>
    </div>
  )
}
