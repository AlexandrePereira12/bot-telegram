import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ConfirmDialog, ErrorBox, Loading, Panel, datetime } from '../components'
import { api } from '../services/api'
import type { AiIntegration, AiIntegrationTest, AiProvider } from '../types'

/** Os dois provedores aceitos, com o que a pessoa precisa saber para escolher
 *  antes de sair procurando chave. O formato da chamada muda entre eles — por
 *  isso é escolha, e não campo livre. */
const PROVEDORES: {
  value: AiProvider
  label: string
  ajuda: string
  onde: string
  exemplo: string
}[] = [
  {
    value: 'GEMINI',
    label: 'Google Gemini',
    ajuda: 'Tem camada gratuita com limite de requisições por minuto.',
    onde: 'aistudio.google.com/apikey',
    exemplo: 'gemini-2.5-flash',
  },
  {
    value: 'OPENROUTER',
    label: 'OpenRouter',
    ajuda: 'Catálogo com vários modelos; os terminados em ":free" não cobram.',
    onde: 'openrouter.ai/keys',
    exemplo: 'google/gemma-4-31b-it:free',
  },
]

export default function Settings() {
  const queryClient = useQueryClient()
  const [provider, setProvider] = useState<AiProvider>('GEMINI')
  const [model, setModel] = useState('gemini-2.5-flash')
  const [apiKey, setApiKey] = useState('')
  const [ativa, setAtiva] = useState(true)
  const [removendo, setRemovendo] = useState(false)

  const integracao = useQuery({
    queryKey: ['settings', 'ai'],
    queryFn: () => api<AiIntegration>('/settings/ai'),
  })

  // Carrega o que já está salvo — menos a chave, que o servidor nunca devolve.
  useEffect(() => {
    const dados = integracao.data
    if (!dados?.configured) return
    if (dados.provider) setProvider(dados.provider)
    if (dados.model) setModel(dados.model)
    setAtiva(dados.is_active)
  }, [integracao.data])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['settings'] })

  const salvar = useMutation({
    mutationFn: () =>
      api<AiIntegration>('/settings/ai', {
        method: 'PUT',
        body: JSON.stringify({
          provider,
          model,
          // Campo em branco numa integração existente significa "mantém a
          // chave atual" — a tela nunca precisa ter o segredo em mãos.
          api_key: apiKey || null,
          is_active: ativa,
        }),
      }),
    onSuccess: () => {
      setApiKey('')
      invalidate()
    },
  })

  const testar = useMutation({
    mutationFn: () => api<AiIntegrationTest>('/settings/ai/test', { method: 'POST' }),
    onSuccess: invalidate,
  })

  const remover = useMutation({
    mutationFn: () => api<void>('/settings/ai', { method: 'DELETE' }),
    onSuccess: () => {
      setRemovendo(false)
      setApiKey('')
      invalidate()
    },
  })

  const dados = integracao.data
  const configurada = Boolean(dados?.configured)
  const escolhido = PROVEDORES.find((p) => p.value === provider)!

  return (
    <>
      <h1>Configurações</h1>
      <p className="page-sub">
        Integrações da instalação. A chave de API é guardada cifrada e nunca é
        exibida de novo — só a máscara.
      </p>

      <Panel title="Atendimento por IA">
        {integracao.isLoading && <Loading />}
        {integracao.isError && <ErrorBox error={integracao.error} />}

        {!integracao.isLoading && (
          <>
            <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
              Com uma integração ativa, quem pede atendimento no Telegram
              conversa primeiro com a IA; uma pessoa assume quando o lead
              insistir em falar com o time. Sem integração, o lead vai direto
              para a fila — o comportamento de sempre.
            </p>

            <div className="estado-integracao">
              <span className={`badge ${configurada && dados?.is_active ? 'ok' : ''}`}>
                {!configurada
                  ? 'não configurada'
                  : dados?.is_active
                    ? 'ativa'
                    : 'configurada, desativada'}
              </span>
              {configurada && (
                <>
                  <span className="muted">
                    chave <code>{dados?.api_key_masked}</code>
                  </span>
                  <span className="muted">
                    {dados?.last_checked_at
                      ? `último teste em ${datetime(dados.last_checked_at)}`
                      : 'nunca testada'}
                  </span>
                </>
              )}
            </div>

            {configurada && dados?.last_error && (
              <p className="error" style={{ marginTop: 8 }}>
                {dados.last_error}
              </p>
            )}

            <div className="field">
              <label>Provedor</label>
              <select
                value={provider}
                onChange={(e) => {
                  const novo = e.target.value as AiProvider
                  setProvider(novo)
                  // Modelo de um provedor não existe no outro: trocar sem
                  // ajustar o campo deixaria a integração quebrada.
                  setModel(PROVEDORES.find((p) => p.value === novo)!.exemplo)
                }}
              >
                {PROVEDORES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
              <small className="muted">
                {escolhido.ajuda} Chave em <code>{escolhido.onde}</code>.
              </small>
            </div>

            <div className="field">
              <label>Modelo</label>
              <input
                value={model}
                placeholder={escolhido.exemplo}
                onChange={(e) => setModel(e.target.value)}
              />
              <small className="muted">
                Identificador exato do provedor. Modelo gratuito sai do catálogo
                de vez em quando — quando isso acontece, é aqui que se troca.
              </small>
            </div>

            <div className="field">
              <label>Chave de API</label>
              <input
                type="password"
                value={apiKey}
                autoComplete="off"
                placeholder={
                  configurada
                    ? 'deixe em branco para manter a chave atual'
                    : 'cole a chave do provedor'
                }
                onChange={(e) => setApiKey(e.target.value)}
              />
              <small className="muted">
                Guardada cifrada no banco. Depois de salva não aparece mais em
                nenhuma tela nem em log — para trocar, cole uma nova.
              </small>
            </div>

            <label className="linha-check">
              <input
                type="checkbox"
                checked={ativa}
                onChange={(e) => setAtiva(e.target.checked)}
              />
              Atendimento por IA ativo
            </label>

            {salvar.isError && <ErrorBox error={salvar.error} />}
            {testar.isError && <ErrorBox error={testar.error} />}
            {remover.isError && <ErrorBox error={remover.error} />}

            {testar.data && (
              <p
                className={testar.data.ok ? 'muted' : 'error'}
                style={{ marginTop: 10, fontSize: 12.5 }}
              >
                {testar.data.ok
                  ? `Conexão funcionando. Resposta do modelo: "${testar.data.sample}"`
                  : testar.data.detail}
              </p>
            )}

            <div className="toolbar" style={{ marginTop: 14, marginBottom: 0 }}>
              <button
                onClick={() => salvar.mutate()}
                disabled={salvar.isPending || !model || (!configurada && !apiKey)}
              >
                {salvar.isPending ? 'salvando…' : 'Salvar'}
              </button>
              <button
                className="secondary"
                onClick={() => testar.mutate()}
                disabled={!configurada || testar.isPending}
                title="faz uma chamada real ao provedor com a chave guardada"
              >
                {testar.isPending ? 'testando…' : 'Testar conexão'}
              </button>
              {configurada && (
                <button
                  className="danger"
                  onClick={() => setRemovendo(true)}
                  disabled={remover.isPending}
                >
                  Remover integração
                </button>
              )}
            </div>
          </>
        )}
      </Panel>

      <ConfirmDialog
        open={removendo}
        title="Remover integração de IA"
        confirmLabel="Remover"
        danger
        busy={remover.isPending}
        onConfirm={() => remover.mutate()}
        onClose={() => setRemovendo(false)}
      >
        A chave é apagada e o atendimento por IA para na hora: quem pedir
        atendimento passa a entrar direto na fila humana. As conversas já
        atendidas continuam no histórico.
      </ConfirmDialog>
    </>
  )
}
