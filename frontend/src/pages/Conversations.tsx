import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Empty, ErrorBox, Loading, Panel, StatusBadge, datetime } from '../components'
import { api, uploadMedia } from '../services/api'
import type {
  Conversation,
  ConversationDetail,
  ConversationOutcome,
  Operator,
} from '../types'

function OutcomeBadge({ outcome }: { outcome: ConversationOutcome | null }) {
  if (!outcome) return null
  return (
    <span className={`badge ${outcome === 'CONVERTED' ? 'ok' : 'danger'}`}>
      {outcome === 'CONVERTED' ? 'deu certo' : 'não converteu'}
    </span>
  )
}

export default function Conversations() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<number | null>(null)
  const [reply, setReply] = useState('')
  const [anexo, setAnexo] = useState<{ path: string; type: 'photo' | 'video' } | null>(
    null,
  )
  const [encerrando, setEncerrando] = useState(false)
  // Encerrados saem da fila e ficam no histórico, que abre sob demanda.
  const [verHistorico, setVerHistorico] = useState(false)

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
    }) =>
      api<Conversation>(`/conversations/${payload.id}/close`, {
        method: 'POST',
        body: JSON.stringify({
          outcome: payload.outcome,
          reason: payload.reason || null,
          value: payload.value ? Number(payload.value) : null,
          currency: payload.value ? 'BRL' : null,
        }),
      }),
    onSuccess: () => {
      setEncerrando(false)
      setSelected(null)
      invalidate()
    },
  })

  const send = useMutation({
    mutationFn: (id: number) =>
      api(`/conversations/${id}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          content: reply,
          media_path: anexo?.path ?? null,
          media_type: anexo?.type ?? null,
        }),
      }),
    onSuccess: () => {
      setReply('')
      setAnexo(null)
      invalidate()
    },
  })

  const enviarAnexo = useMutation({
    mutationFn: (file: File) => uploadMedia(file),
    onSuccess: (r) => setAnexo({ path: r.media_path, type: r.media_type }),
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
              </>
            )}
          </div>

          {assign.isError && <ErrorBox error={assign.error} />}

          {encerrando && aberta && (
            <CloseForm
              onClose={(outcome, reason, value) =>
                close.mutate({ id: detail.data!.id, outcome, reason, value })
              }
              busy={close.isPending}
              error={close.error}
            />
          )}

          <div className="chat">
            {detail.data.messages.length === 0 && <Empty text="sem mensagens" />}
            {detail.data.messages.map((m) => (
              <div className={`bubble ${m.sender_type}`} key={m.id}>
                {m.media_type && (
                  <span className="badge" style={{ marginBottom: 4, display: 'inline-block' }}>
                    {m.media_type === 'photo' ? 'imagem' : 'vídeo'}
                  </span>
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
                <div style={{ marginTop: 10 }}>
                  <span className="badge">{anexo.type}</span>{' '}
                  <span className="muted" style={{ fontSize: 12 }}>
                    anexo pronto para enviar
                  </span>{' '}
                  <button
                    className="secondary"
                    style={{ padding: '2px 8px', fontSize: 11 }}
                    onClick={() => setAnexo(null)}
                  >
                    remover
                  </button>
                </div>
              )}

              <form
                style={{ marginTop: 12, display: 'flex', gap: 8 }}
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
                  title="anexar imagem ou vídeo"
                >
                  {enviarAnexo.isPending ? '…' : '📎'}
                  <input
                    type="file"
                    accept="image/*,video/*"
                    style={{ display: 'none' }}
                    disabled={!minha}
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) enviarAnexo.mutate(f)
                    }}
                  />
                </label>
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

/** Formulário de encerramento: exige o desfecho, valor e motivo são opcionais. */
function CloseForm({
  onClose,
  busy,
  error,
}: {
  onClose: (outcome: ConversationOutcome, reason: string, value: string) => void
  busy: boolean
  error: unknown
}) {
  const [outcome, setOutcome] = useState<ConversationOutcome>('CONVERTED')
  const [reason, setReason] = useState('')
  const [value, setValue] = useState('')

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 14,
        margin: '12px 0',
      }}
    >
      <h2 style={{ fontSize: 13, marginTop: 0 }}>Como terminou o atendimento?</h2>

      <div className="toolbar" style={{ marginBottom: 10 }}>
        <button
          className={outcome === 'CONVERTED' ? '' : 'secondary'}
          onClick={() => setOutcome('CONVERTED')}
          type="button"
        >
          Deu certo (converteu)
        </button>
        <button
          className={outcome === 'NOT_CONVERTED' ? '' : 'secondary'}
          onClick={() => setOutcome('NOT_CONVERTED')}
          type="button"
        >
          Não converteu
        </button>
      </div>

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

      <div className="field">
        <label>Observação (opcional)</label>
        <input
          value={reason}
          maxLength={255}
          placeholder={
            outcome === 'CONVERTED' ? 'fechou o plano anual' : 'fora do perfil'
          }
          onChange={(e) => setReason(e.target.value)}
        />
      </div>

      {error != null && <ErrorBox error={error} />}

      <button onClick={() => onClose(outcome, reason, value)} disabled={busy}>
        {busy ? 'encerrando…' : 'Confirmar encerramento'}
      </button>
      <small className="muted" style={{ fontSize: 11, display: 'block', marginTop: 8 }}>
        Encerrado, sai da fila e vai para o histórico. Se o lead voltar a escrever,
        inicia um atendimento novo.
      </small>
    </div>
  )
}
