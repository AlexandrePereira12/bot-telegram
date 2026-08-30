import { useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { ThemeToggle, initials } from './components'
import { api, clearTokens, getAccessToken, subscribeAuth } from './services/api'
import type { Operator } from './types'
import Analytics from './pages/Analytics'
import Campaigns from './pages/Campaigns'
import Content from './pages/Content'
import Conversations from './pages/Conversations'
import Dashboard from './pages/Dashboard'
import Funnel from './pages/Funnel'
import LeadDetail from './pages/LeadDetail'
import Leads from './pages/Leads'
import Login from './pages/Login'
import Operators from './pages/Operators'

/** Nome curto de cada perfil. O valor cru (ADMIN, SUPPORT) é o que o
 *  backend usa; na tela ele vira o rótulo em português. */
const ROLE_LABEL: Record<string, string> = {
  ADMIN: 'Administrador',
  MANAGER: 'Gestor',
  ANALYST: 'Analista',
  OPERATOR: 'Operador',
  SUPPORT: 'Suporte',
}

/** Permissões espelham o RBAC do backend — o servidor continua sendo a
 *  autoridade; isto só evita mostrar link para tela que daria 403. */
const NAV = [
  { to: '/dashboard', label: 'Dashboard', roles: ['ADMIN', 'MANAGER', 'ANALYST'] },
  { to: '/campaigns', label: 'Campanhas', roles: ['ADMIN', 'MANAGER', 'ANALYST'] },
  { to: '/content', label: 'Conteúdo do bot', roles: ['ADMIN', 'MANAGER'] },
  { to: '/funnel', label: 'Funil', roles: ['ADMIN', 'MANAGER', 'ANALYST'] },
  {
    to: '/leads',
    label: 'Leads',
    roles: ['ADMIN', 'MANAGER', 'ANALYST', 'OPERATOR', 'SUPPORT'],
  },
  {
    to: '/conversations',
    label: 'Conversas',
    roles: ['ADMIN', 'MANAGER', 'OPERATOR', 'SUPPORT'],
  },
  { to: '/analytics', label: 'Analytics', roles: ['ADMIN', 'MANAGER', 'ANALYST'] },
  { to: '/operators', label: 'Usuários', roles: ['ADMIN'] },
]

function Shell({ operator }: { operator: Operator }) {
  const navigate = useNavigate()
  const visible = NAV.filter((item) => item.roles.includes(operator.role))

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">Tráfego · Telegram</div>

        <div className="identity">
          <span className="avatar" aria-hidden="true">
            {initials(operator.full_name, operator.email)}
          </span>
          <div className="identity-text">
            <strong>{operator.full_name ?? operator.email.split('@')[0]}</strong>
            <span className="muted" title={operator.email}>
              {operator.email}
            </span>
          </div>
          <span className="badge">{ROLE_LABEL[operator.role] ?? operator.role}</span>
        </div>
        <nav className="nav">
          {visible.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <ThemeToggle />
          <button
            className="secondary"
            onClick={() => {
              clearTokens()
              navigate('/login')
            }}
          >
            Sair
          </button>
        </div>
      </aside>

      <main className="content">
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/campaigns" element={<Campaigns />} />
          <Route path="/content" element={<Content />} />
          <Route path="/funnel" element={<Funnel />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadDetail />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/operators" element={<Operators />} />
          <Route path="*" element={<Navigate to={visible[0]?.to ?? '/leads'} replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  // Assina as mudanças de token: sem isso o valor é lido uma vez no render e
  // o login não re-renderiza a aplicação.
  const token = useSyncExternalStore(subscribeAuth, getAccessToken, () => null)
  const hasToken = Boolean(token)

  const { data: operator, isLoading, isError } = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Operator>('/auth/me'),
    enabled: hasToken,
  })

  if (!hasToken || isError) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  if (isLoading || !operator) {
    return <div style={{ padding: 32 }} className="muted">carregando…</div>
  }

  return <Shell operator={operator} />
}
