import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  ConfirmDialog,
  Empty,
  ErrorBox,
  Loading,
  Modal,
  Panel,
  datetime,
} from '../components'
import { api } from '../services/api'
import type { Operator, OperatorAdmin, OperatorCreated } from '../types'

type Role = Operator['role']

/** Os cinco perfis do RBAC do backend (`PERMISSIONS` em auth_service.py). A
 *  descrição existe para que a escolha não vire adivinhação na hora do
 *  cadastro — quem cadastra precisa saber o que está liberando. */
const ROLES: { value: Role; label: string; description: string }[] = [
  {
    value: 'ADMIN',
    label: 'Administrador',
    description: 'Acesso total, incluindo cadastro de usuários. Exige autenticador (2FA).',
  },
  {
    value: 'MANAGER',
    label: 'Gestor',
    description: 'Campanhas, conteúdo do bot e relatórios. Não cadastra usuários.',
  },
  {
    value: 'ANALYST',
    label: 'Analista',
    description: 'Somente leitura de campanhas, leads e analytics.',
  },
  {
    value: 'OPERATOR',
    label: 'Operador',
    description: 'Atende conversas e vê leads. Sem acesso a analytics.',
  },
  {
    value: 'SUPPORT',
    label: 'Suporte',
    description: 'Mesmo alcance do operador, voltado ao atendimento.',
  },
]

const ROLE_LABEL = new Map(ROLES.map((item) => [item.value, item.label]))
const descricao = (role: Role) => ROLES.find((item) => item.value === role)!.description

/** Ação destrutiva pendente de confirmação. */
type Pendente =
  | { tipo: 'toggle'; alvo: OperatorAdmin }
  | { tipo: 'delete'; alvo: OperatorAdmin }
  | { tipo: 'reset2fa'; alvo: OperatorAdmin }

function nomeDe(item: OperatorAdmin): string {
  return item.full_name ?? item.email
}

export default function Operators() {
  const queryClient = useQueryClient()
  const [cadastrando, setCadastrando] = useState(false)
  const [editando, setEditando] = useState<OperatorAdmin | null>(null)
  const [pendente, setPendente] = useState<Pendente | null>(null)
  const [criado, setCriado] = useState<OperatorCreated | null>(null)

  const operators = useQuery({
    queryKey: ['operators'],
    queryFn: () => api<OperatorAdmin[]>('/operators'),
  })
  // Mesma chave que o App usa: vem do cache, sem requisição extra.
  const eu = useQuery({ queryKey: ['me'], queryFn: () => api<Operator>('/auth/me') })

  const recarregar = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['operators'] }),
    [queryClient],
  )

  const acao = useMutation<unknown, Error, Pendente>({
    mutationFn: (item: Pendente) => {
      if (item.tipo === 'delete') {
        return api<void>(`/operators/${item.alvo.id}`, { method: 'DELETE' })
      }
      if (item.tipo === 'reset2fa') {
        return api<OperatorAdmin>(`/operators/${item.alvo.id}/reset-2fa`, { method: 'POST' })
      }
      return api<OperatorAdmin>(`/operators/${item.alvo.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !item.alvo.is_active }),
      })
    },
    onSuccess: () => {
      setPendente(null)
      recarregar()
    },
  })

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Usuários</h1>
          <p className="page-sub" style={{ marginBottom: 0 }}>
            Quem entra no painel e com qual perfil. O perfil vale no servidor:
            esconder um item do menu não é o que bloqueia o acesso.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCriado(null)
            setCadastrando(true)
          }}
        >
          Novo usuário
        </button>
      </div>

      {criado && (
        <Panel title="Usuário cadastrado">
          <SenhaGerada criado={criado} onDismiss={() => setCriado(null)} />
        </Panel>
      )}

      <Panel title="Usuários do painel">
        {operators.isLoading && <Loading />}
        {operators.isError && <ErrorBox error={operators.error} />}
        {operators.data && operators.data.length === 0 && <Empty />}
        {operators.data && operators.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Usuário</th>
                <th>Perfil</th>
                <th>Acesso</th>
                <th>Criado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {operators.data.map((item) => {
                // Perfil, acesso e exclusão da própria conta são recusados
                // pelo servidor. Esconder aqui evita oferecer um clique que
                // só resultaria em erro.
                const souEu = item.id === eu.data?.id
                return (
                <tr key={item.id}>
                  <td>
                    {item.full_name ? (
                      <>
                        <strong>{item.full_name}</strong>{' '}
                        <span className="muted">{item.email}</span>
                      </>
                    ) : (
                      item.email
                    )}
                    {souEu && <span className="badge" style={{ marginLeft: 8 }}>você</span>}
                  </td>
                  <td>{ROLE_LABEL.get(item.role) ?? item.role}</td>
                  <td>
                    {!item.is_active ? (
                      <span className="badge danger">desativado</span>
                    ) : item.role === 'ADMIN' && item.totp_pending ? (
                      <span className="badge warn">2FA pendente</span>
                    ) : (
                      <span className="badge ok">ativo</span>
                    )}
                  </td>
                  <td className="muted">{datetime(item.created_at)}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="link"
                        onClick={() => setEditando(item)}
                      >
                        editar
                      </button>
                      {!souEu && (
                        <button
                          type="button"
                          className="link"
                          onClick={() => setPendente({ tipo: 'toggle', alvo: item })}
                        >
                          {item.is_active ? 'desativar' : 'reativar'}
                        </button>
                      )}
                      {!souEu && item.role === 'ADMIN' && !item.totp_pending && (
                        <button
                          type="button"
                          className="link"
                          onClick={() => setPendente({ tipo: 'reset2fa', alvo: item })}
                        >
                          reiniciar 2FA
                        </button>
                      )}
                      {!souEu && (
                        <button
                          type="button"
                          className="link danger"
                          onClick={() => setPendente({ tipo: 'delete', alvo: item })}
                        >
                          excluir
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <FormularioCadastro
        open={cadastrando}
        onClose={() => setCadastrando(false)}
        onCreated={(novo) => {
          setCadastrando(false)
          setCriado(novo)
          recarregar()
        }}
      />

      <FormularioEdicao
        alvo={editando}
        souEu={editando?.id === eu.data?.id}
        onClose={() => setEditando(null)}
        onSaved={() => {
          setEditando(null)
          recarregar()
        }}
      />

      <ConfirmDialog
        open={pendente !== null}
        title={
          pendente?.tipo === 'delete'
            ? 'Excluir usuário'
            : pendente?.tipo === 'reset2fa'
              ? 'Reiniciar autenticador'
              : pendente?.alvo.is_active
                ? 'Desativar acesso'
                : 'Reativar acesso'
        }
        confirmLabel={
          pendente?.tipo === 'delete'
            ? 'Excluir definitivamente'
            : pendente?.tipo === 'reset2fa'
              ? 'Reiniciar 2FA'
              : pendente?.alvo.is_active
                ? 'Desativar'
                : 'Reativar'
        }
        danger={pendente?.tipo === 'delete' || Boolean(pendente?.alvo.is_active)}
        busy={acao.isPending}
        onConfirm={() => pendente && acao.mutate(pendente)}
        onClose={() => {
          setPendente(null)
          acao.reset()
        }}
      >
        {pendente && (
          <>
            <p>
              <strong>{nomeDe(pendente.alvo)}</strong>
            </p>
            {pendente.tipo === 'delete' && (
              <p className="muted">
                A exclusão só é possível enquanto a pessoa não tiver histórico —
                atendimento, mensagem ou registro de auditoria. Quem já trabalhou
                no sistema não é apagado: nesse caso, desative o acesso e o
                rastro de quem fez o quê continua íntegro.
              </p>
            )}
            {pendente.tipo === 'toggle' && pendente.alvo.is_active && (
              <p className="muted">
                O acesso cai na hora, sem esperar o token expirar. O cadastro e o
                histórico ficam preservados e dá para reativar depois.
              </p>
            )}
            {pendente.tipo === 'toggle' && !pendente.alvo.is_active && (
              <p className="muted">
                A pessoa volta a entrar com a mesma senha e o mesmo perfil.
              </p>
            )}
            {pendente.tipo === 'reset2fa' && (
              <p className="muted">
                Use quando a pessoa trocou ou perdeu o celular. O autenticador
                atual é descartado e, no próximo login, o painel mostra um QR
                novo para ela cadastrar. Ninguém vê o segredo antigo.
              </p>
            )}
            {acao.isError && <ErrorBox error={acao.error} context="não foi possível" />}
          </>
        )}
      </ConfirmDialog>
    </>
  )
}

function SenhaGerada({
  criado,
  onDismiss,
}: {
  criado: OperatorCreated
  onDismiss: () => void
}) {
  const [copiado, setCopiado] = useState(false)

  return (
    <>
      <p style={{ marginTop: 0 }}>
        <strong>{criado.email}</strong> · {ROLE_LABEL.get(criado.role) ?? criado.role}
      </p>
      {criado.generated_password ? (
        <>
          <p className="muted" style={{ fontSize: 12 }}>
            Senha gerada pelo servidor. Ela aparece uma única vez — copie e
            entregue agora, não é recuperável depois.
          </p>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <code
              className="mono"
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '8px 12px',
                wordBreak: 'break-all',
              }}
            >
              {criado.generated_password}
            </code>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                navigator.clipboard
                  ?.writeText(criado.generated_password ?? '')
                  .then(() => setCopiado(true))
                  .catch(() => setCopiado(false))
              }}
            >
              {copiado ? 'copiado' : 'copiar senha'}
            </button>
            <button type="button" className="secondary" onClick={onDismiss}>
              Já anotei
            </button>
          </div>
        </>
      ) : (
        <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
          Cadastrado com a senha que você informou.
        </p>
      )}
    </>
  )
}

function FormularioCadastro({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (novo: OperatorCreated) => void
}) {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<Role>('OPERATOR')
  const [password, setPassword] = useState('')

  const criar = useMutation({
    mutationFn: () =>
      api<OperatorCreated>('/operators', {
        method: 'POST',
        body: JSON.stringify({
          email: email.trim(),
          full_name: fullName.trim() || null,
          role,
          // Sem senha informada, o servidor gera uma forte e devolve uma vez.
          password: password ? password : null,
        }),
      }),
    onSuccess: onCreated,
  })

  // Fechar pelo ESC não passa pelo React: limpar aqui evita reabrir o modal
  // com o que foi digitado na tentativa anterior.
  function fechar() {
    setEmail('')
    setFullName('')
    setPassword('')
    setRole('OPERATOR')
    criar.reset()
    onClose()
  }

  return (
    <Modal open={open} title="Novo usuário" onClose={fechar} width={440}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          criar.mutate()
        }}
      >
        <div className="field">
          <label htmlFor="op-email">E-mail</label>
          <input
            id="op-email"
            type="email"
            value={email}
            autoComplete="off"
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </div>

        <div className="field">
          <label htmlFor="op-nome">Nome (opcional)</label>
          <input id="op-nome" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>

        <div className="field">
          <label htmlFor="op-perfil">Perfil</label>
          <select
            id="op-perfil"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            {ROLES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <small className="muted" style={{ fontSize: 11.5, display: 'block', marginTop: 5 }}>
            {descricao(role)}
          </small>
        </div>

        <div className="field">
          <label htmlFor="op-senha">Senha (opcional)</label>
          <input
            id="op-senha"
            type="password"
            value={password}
            autoComplete="new-password"
            minLength={8}
            placeholder="deixe vazio para o servidor gerar"
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {role === 'ADMIN' && (
          <p className="muted" style={{ fontSize: 12 }}>
            O autenticador é cadastrado pelo próprio dono no primeiro login — o
            painel mostra o QR na hora. O segredo nunca passa por aqui.
          </p>
        )}

        {criar.isError && <ErrorBox error={criar.error} context="não foi possível cadastrar" />}

        <div className="modal-actions">
          <button type="button" className="secondary" onClick={fechar}>
            Cancelar
          </button>
          <button type="submit" disabled={criar.isPending || !email.trim()}>
            {criar.isPending ? 'cadastrando…' : 'Cadastrar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function FormularioEdicao({
  alvo,
  souEu,
  onClose,
  onSaved,
}: {
  alvo: OperatorAdmin | null
  souEu: boolean
  onClose: () => void
  onSaved: () => void
}) {
  // `key` remonta o formulário a cada alvo: sem isso o estado do anterior
  // aparece ao abrir o próximo.
  return alvo ? (
    <EdicaoInterna key={alvo.id} alvo={alvo} souEu={souEu} onClose={onClose} onSaved={onSaved} />
  ) : (
    <Modal open={false} title="Editar usuário" onClose={onClose}>
      <span />
    </Modal>
  )
}

function EdicaoInterna({
  alvo,
  souEu,
  onClose,
  onSaved,
}: {
  alvo: OperatorAdmin
  souEu: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [fullName, setFullName] = useState(alvo.full_name ?? '')
  const [role, setRole] = useState<Role>(alvo.role)

  const salvar = useMutation({
    mutationFn: () =>
      api<OperatorAdmin>(`/operators/${alvo.id}`, {
        method: 'PATCH',
        // Na própria conta só o nome viaja: mandar `role` igual ao atual
        // ainda cairia no guarda de alteração sobre si mesmo.
        body: JSON.stringify(
          souEu ? { full_name: fullName.trim() || null } : { full_name: fullName.trim() || null, role },
        ),
      }),
    onSuccess: onSaved,
  })

  return (
    <Modal open title={`Editar ${nomeDe(alvo)}`} onClose={onClose} width={440}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          salvar.mutate()
        }}
      >
        <div className="field">
          <label htmlFor="ed-email">E-mail</label>
          <input id="ed-email" value={alvo.email} disabled />
          <small className="muted" style={{ fontSize: 11.5 }}>
            O e-mail identifica a conta e não é alterado por aqui.
          </small>
        </div>

        <div className="field">
          <label htmlFor="ed-nome">Nome</label>
          <input
            id="ed-nome"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            autoFocus
          />
        </div>

        <div className="field">
          <label htmlFor="ed-perfil">Perfil</label>
          <select
            id="ed-perfil"
            value={role}
            disabled={souEu}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            {ROLES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <small className="muted" style={{ fontSize: 11.5, display: 'block', marginTop: 5 }}>
            {souEu
              ? 'O próprio perfil não é alterado por aqui: um administrador que se rebaixa perde o acesso na mesma hora — e, se for o único, tranca a instalação.'
              : descricao(role)}
          </small>
        </div>

        {role === 'ADMIN' && alvo.role !== 'ADMIN' && (
          <p className="muted" style={{ fontSize: 12 }}>
            Promover a administrador passa a exigir autenticador: o QR aparece
            para essa pessoa no próximo login.
          </p>
        )}

        {salvar.isError && <ErrorBox error={salvar.error} context="não foi possível salvar" />}

        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" disabled={salvar.isPending}>
            {salvar.isPending ? 'salvando…' : 'Salvar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
