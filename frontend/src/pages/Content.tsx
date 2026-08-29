import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Empty, ErrorBox, Loading, Panel } from '../components'
import { api, uploadMedia } from '../services/api'
import type { Campaign, FunnelStepContent, QualificationOption } from '../types'

const STEP_LABEL: Record<string, string> = {
  WELCOME: 'Boas-vindas',
  CONSENT: 'Termos de consentimento',
  CONSENT_REQUIRED: 'Recusou os termos',
  AGE_GATE: 'Verificação de idade',
  AGE_REJECTED: 'Reprovado na idade',
  QUALIFICATION: 'Pergunta de qualificação',
  INFORMATION: 'Resposta de informação',
  HUMAN_SUPPORT: 'Entrou na fila de atendimento',
  FOLLOWUP: 'Mensagem de retomada',
}

/** Variáveis que o texto de cada etapa aceita. */
const STEP_VARS: Record<string, string[]> = {
  WELCOME: ['{name}', '{company}'],
  CONSENT: ['{version}'],
  AGE_GATE: ['{min_age}'],
  AGE_REJECTED: ['{min_age}'],
  INFORMATION: ['{interest}'],
}

const ORIGIN_BADGE: Record<string, { texto: string; classe: string }> = {
  campanha: { texto: 'texto próprio', classe: 'ok' },
  global: { texto: 'usando o padrão', classe: '' },
  codigo: { texto: 'padrão do sistema', classe: 'warn' },
}

export default function Content() {
  const queryClient = useQueryClient()
  // null = editando o padrão global.
  const [campaignId, setCampaignId] = useState<number | null>(null)
  const [aba, setAba] = useState<'textos' | 'opcoes'>('textos')

  const campanhas = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api<Campaign[]>('/campaigns'),
  })

  const qs = campaignId ? `?campaign_id=${campaignId}` : ''

  const steps = useQuery({
    queryKey: ['content-steps', campaignId],
    queryFn: () => api<FunnelStepContent[]>(`/content/steps${qs}`),
  })
  const options = useQuery({
    queryKey: ['content-options', campaignId],
    queryFn: () => api<QualificationOption[]>(`/content/options${qs}`),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['content-steps', campaignId] })
    queryClient.invalidateQueries({ queryKey: ['content-options', campaignId] })
  }

  return (
    <>
      <h1>Conteúdo do bot</h1>
      <p className="page-sub">
        O que o bot fala em cada etapa. Escolha uma campanha para dar a ela uma
        conversa própria — sem texto próprio, ela usa o padrão.
      </p>

      <Panel title="Editando">
        <div className="toolbar">
          <div className="field">
            <label>Campanha</label>
            <select
              value={campaignId ?? ''}
              onChange={(e) =>
                setCampaignId(e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">Padrão (todas as campanhas)</option>
              {campanhas.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <button
            className={aba === 'textos' ? '' : 'secondary'}
            onClick={() => setAba('textos')}
          >
            Mensagens
          </button>
          <button
            className={aba === 'opcoes' ? '' : 'secondary'}
            onClick={() => setAba('opcoes')}
          >
            Opções do menu
          </button>
        </div>
      </Panel>

      {aba === 'textos' ? (
        <>
          {steps.isLoading && <Loading />}
          {steps.isError && <ErrorBox error={steps.error} />}
          {steps.data?.map((step) => (
            <StepEditor
              key={step.step}
              step={step}
              campaignId={campaignId}
              onSaved={invalidate}
            />
          ))}
        </>
      ) : (
        <OptionsEditor
          options={options.data ?? []}
          loading={options.isLoading}
          campaignId={campaignId}
          onSaved={invalidate}
        />
      )}
    </>
  )
}

function StepEditor({
  step,
  campaignId,
  onSaved,
}: {
  step: FunnelStepContent
  campaignId: number | null
  onSaved: () => void
}) {
  const [body, setBody] = useState(step.body)
  const [mediaPath, setMediaPath] = useState(step.media_path)
  const [mediaType, setMediaType] = useState(step.media_type)
  const [erro, setErro] = useState<string | null>(null)

  // Etapa de efeito legal só existe globalmente.
  const bloqueada = campaignId !== null && !step.editable_per_campaign
  const alterado =
    body !== step.body ||
    mediaPath !== step.media_path ||
    mediaType !== step.media_type

  const salvar = useMutation({
    mutationFn: () =>
      api(`/content/steps${campaignId ? `?campaign_id=${campaignId}` : ''}`, {
        method: 'PUT',
        body: JSON.stringify({
          step: step.step,
          body,
          media_path: mediaPath,
          media_type: mediaType,
        }),
      }),
    onSuccess: () => {
      setErro(null)
      onSaved()
    },
    onError: (e) => setErro((e as Error).message),
  })

  const restaurar = useMutation({
    mutationFn: () =>
      api(`/content/steps/${step.step}?campaign_id=${campaignId}`, {
        method: 'DELETE',
      }),
    onSuccess: onSaved,
  })

  const enviarMidia = useMutation({
    mutationFn: (file: File) => uploadMedia(file),
    onSuccess: (r) => {
      setMediaPath(r.media_path)
      setMediaType(r.media_type)
      setErro(null)
    },
    onError: (e) => setErro((e as Error).message),
  })

  const badge = ORIGIN_BADGE[step.origin]

  return (
    <section className="panel">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 10,
        }}
      >
        <h2 style={{ margin: 0 }}>{STEP_LABEL[step.step] ?? step.step}</h2>
        <span className={`badge ${badge.classe}`}>{badge.texto}</span>
      </div>

      {bloqueada && (
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          Esta etapa só pode ser editada no padrão. O aceite é auditado por
          versão dos termos — se o texto variasse por campanha, o registro
          deixaria de provar o que a pessoa aceitou.
        </p>
      )}

      <textarea
        rows={4}
        value={body}
        disabled={bloqueada}
        onChange={(e) => setBody(e.target.value)}
        style={{ fontFamily: 'inherit', resize: 'vertical' }}
      />

      {STEP_VARS[step.step] && (
        <small className="muted" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
          variáveis disponíveis: {STEP_VARS[step.step].join(', ')}
        </small>
      )}

      {mediaPath && (
        <div style={{ marginTop: 8 }}>
          <span className="badge">{mediaType}</span>{' '}
          <span className="muted" style={{ fontSize: 12 }}>
            mídia anexada
          </span>{' '}
          <button
            className="secondary"
            style={{ padding: '2px 8px', fontSize: 11 }}
            onClick={() => {
              setMediaPath(null)
              setMediaType(null)
            }}
          >
            remover
          </button>
        </div>
      )}

      {erro && <p className="error">{erro}</p>}

      {!bloqueada && (
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          <button onClick={() => salvar.mutate()} disabled={!alterado || salvar.isPending}>
            {salvar.isPending ? 'salvando…' : 'Salvar'}
          </button>

          <label className="btn secondary" style={{ cursor: 'pointer' }}>
            {enviarMidia.isPending ? 'enviando…' : 'Anexar imagem/vídeo'}
            <input
              type="file"
              accept="image/*,video/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) enviarMidia.mutate(f)
              }}
            />
          </label>

          {campaignId !== null && step.origin === 'campanha' && (
            <button className="secondary" onClick={() => restaurar.mutate()}>
              Voltar ao padrão
            </button>
          )}
        </div>
      )}
    </section>
  )
}

function OptionsEditor({
  options,
  loading,
  campaignId,
  onSaved,
}: {
  options: QualificationOption[]
  loading: boolean
  campaignId: number | null
  onSaved: () => void
}) {
  const [editando, setEditando] = useState<number | 'nova' | null>(null)

  return (
    <>
      <Panel title="Opções que o lead vê na qualificação">
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          Cada opção pode ter sua própria resposta. Sem resposta configurada, o
          bot usa a mensagem genérica de "Resposta de informação".
        </p>

        {loading && <Loading />}
        {!loading && options.length === 0 && (
          <Empty text="esta campanha usa as opções do padrão" />
        )}

        {options.map((o) =>
          editando === o.id ? (
            <OptionForm
              key={o.id}
              inicial={o}
              campaignId={campaignId}
              onDone={() => {
                setEditando(null)
                onSaved()
              }}
              onCancel={() => setEditando(null)}
            />
          ) : (
            <OptionRow
              key={o.id}
              option={o}
              campaignId={campaignId}
              onEdit={() => setEditando(o.id)}
              onSaved={onSaved}
            />
          ),
        )}
      </Panel>

      {editando === 'nova' ? (
        <OptionForm
          campaignId={campaignId}
          onDone={() => {
            setEditando(null)
            onSaved()
          }}
          onCancel={() => setEditando(null)}
        />
      ) : (
        <button onClick={() => setEditando('nova')}>Adicionar opção</button>
      )}
    </>
  )
}

function OptionRow({
  option,
  campaignId,
  onEdit,
  onSaved,
}: {
  option: QualificationOption
  campaignId: number | null
  onEdit: () => void
  onSaved: () => void
}) {
  const desativar = useMutation({
    mutationFn: () => api(`/content/options/${option.id}`, { method: 'DELETE' }),
    onSuccess: onSaved,
  })

  const ehGlobal = campaignId !== null && option.campaign_id === null

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 12,
        marginBottom: 10,
        opacity: option.is_active ? 1 : 0.55,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <div>
          <strong>{option.label}</strong>{' '}
          <span className="badge">
            {option.target === 'HUMAN_SUPPORT' ? 'vai para atendimento' : 'responde'}
          </span>{' '}
          {!option.is_active && <span className="badge danger">inativa</span>}
          {ehGlobal && <span className="badge">do padrão</span>}
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            {option.target === 'HUMAN_SUPPORT'
              ? 'entra na fila de atendimento'
              : option.response_body || 'usa a mensagem genérica de informação'}
            {option.response_media_type && ` · com ${option.response_media_type}`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
          <button className="secondary" onClick={onEdit}>
            editar
          </button>
          {option.is_active && !ehGlobal && (
            <button
              className="secondary"
              onClick={() => desativar.mutate()}
              disabled={desativar.isPending}
            >
              desativar
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/** Cria ou edita uma opção, incluindo a resposta que ela dispara. */
function OptionForm({
  inicial,
  campaignId,
  onDone,
  onCancel,
}: {
  inicial?: QualificationOption
  campaignId: number | null
  onDone: () => void
  onCancel: () => void
}) {
  const [label, setLabel] = useState(inicial?.label ?? '')
  const [key, setKey] = useState(inicial?.key ?? '')
  const [target, setTarget] = useState(inicial?.target ?? 'INFORMATION')
  const [ordem, setOrdem] = useState(inicial?.sort_order ?? 0)
  const [resposta, setResposta] = useState(inicial?.response_body ?? '')
  const [mediaPath, setMediaPath] = useState(inicial?.response_media_path ?? null)
  const [mediaType, setMediaType] = useState(inicial?.response_media_type ?? null)
  const [erro, setErro] = useState<string | null>(null)

  const qs = campaignId ? `?campaign_id=${campaignId}` : ''

  const salvar = useMutation({
    mutationFn: () =>
      api(`/content/options${qs}`, {
        method: 'PUT',
        body: JSON.stringify({
          // Editar uma opção do padrão a partir de uma campanha cria a versão
          // própria dela; a global segue intacta.
          key: key || label.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 64),
          label,
          target,
          sort_order: ordem,
          is_active: inicial?.is_active ?? true,
          response_body: target === 'INFORMATION' ? resposta || null : null,
          response_media_path: target === 'INFORMATION' ? mediaPath : null,
          response_media_type: target === 'INFORMATION' ? mediaType : null,
        }),
      }),
    onSuccess: onDone,
    onError: (e) => setErro((e as Error).message),
  })

  const enviarMidia = useMutation({
    mutationFn: (file: File) => uploadMedia(file),
    onSuccess: (r) => {
      setMediaPath(r.media_path)
      setMediaType(r.media_type)
      setErro(null)
    },
    onError: (e) => setErro((e as Error).message),
  })

  return (
    <div
      style={{
        border: '1px solid var(--accent)',
        borderRadius: 8,
        padding: 14,
        marginBottom: 12,
      }}
    >
      <div className="toolbar">
        <div className="field" style={{ minWidth: 200 }}>
          <label>Texto do botão</label>
          <input
            value={label}
            placeholder="Ver preços"
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="field">
          <label>Identificador</label>
          <input
            value={key}
            placeholder="ver_precos"
            disabled={Boolean(inicial)}
            onChange={(e) =>
              setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))
            }
          />
        </div>
        <div className="field">
          <label>Ao clicar</label>
          <select
            value={target}
            onChange={(e) => setTarget(e.target.value as typeof target)}
          >
            <option value="INFORMATION">Responder com um texto</option>
            <option value="HUMAN_SUPPORT">Chamar atendimento humano</option>
          </select>
        </div>
        <div className="field" style={{ minWidth: 80 }}>
          <label>Ordem</label>
          <input
            type="number"
            value={ordem}
            onChange={(e) => setOrdem(Number(e.target.value))}
          />
        </div>
      </div>

      {target === 'INFORMATION' ? (
        <div className="field">
          <label>Resposta que o bot envia ao escolherem esta opção</label>
          <textarea
            rows={4}
            value={resposta}
            placeholder="Deixe vazio para usar a mensagem genérica de informação."
            onChange={(e) => setResposta(e.target.value)}
            style={{ fontFamily: 'inherit', resize: 'vertical' }}
          />
          <small className="muted" style={{ fontSize: 11 }}>
            variável disponível: {'{interest}'} (o texto do botão)
          </small>
        </div>
      ) : (
        <p className="muted" style={{ fontSize: 12 }}>
          Esta opção coloca o lead na fila de atendimento — o texto enviado é o
          de "Entrou na fila de atendimento".
        </p>
      )}

      {target === 'INFORMATION' && mediaPath && (
        <div style={{ marginBottom: 10 }}>
          <span className="badge">{mediaType}</span>{' '}
          <span className="muted" style={{ fontSize: 12 }}>
            mídia anexada à resposta
          </span>{' '}
          <button
            className="secondary"
            style={{ padding: '2px 8px', fontSize: 11 }}
            onClick={() => {
              setMediaPath(null)
              setMediaType(null)
            }}
          >
            remover
          </button>
        </div>
      )}

      {erro && <p className="error">{erro}</p>}

      <div className="toolbar" style={{ marginBottom: 0 }}>
        <button onClick={() => salvar.mutate()} disabled={!label || salvar.isPending}>
          {salvar.isPending ? 'salvando…' : 'Salvar opção'}
        </button>
        {target === 'INFORMATION' && (
          <label className="btn secondary" style={{ cursor: 'pointer' }}>
            {enviarMidia.isPending ? 'enviando…' : 'Anexar à resposta'}
            <input
              type="file"
              accept="image/*,video/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) enviarMidia.mutate(f)
              }}
            />
          </label>
        )}
        <button className="secondary" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </div>
  )
}
