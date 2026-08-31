import { useEffect, useState, useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { Icon, Loading, ThemeToggle, initials, type IconName } from './components'
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
import Settings from './pages/Settings'

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
const NAV: { to: string; label: string; icon: IconName; roles: string[] }[] = [
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: 'dashboard',
    roles: ['ADMIN', 'MANAGER', 'ANALYST'],
  },
  {
    to: '/campaigns',
    label: 'Campanhas',
    icon: 'campaigns',
    roles: ['ADMIN', 'MANAGER', 'ANALYST'],
  },
  { to: '/content', label: 'Conteúdo do bot', icon: 'content', roles: ['ADMIN', 'MANAGER'] },
  { to: '/funnel', label: 'Funil', icon: 'funnel', roles: ['ADMIN', 'MANAGER', 'ANALYST'] },
  {
    to: '/leads',
    label: 'Leads',
    icon: 'leads',
    roles: ['ADMIN', 'MANAGER', 'ANALYST', 'OPERATOR', 'SUPPORT'],
  },
  {
    to: '/conversations',
    label: 'Conversas',
    icon: 'conversations',
    roles: ['ADMIN', 'MANAGER', 'OPERATOR', 'SUPPORT'],
  },
  {
    to: '/analytics',
    label: 'Analytics',
    icon: 'analytics',
    roles: ['ADMIN', 'MANAGER', 'ANALYST'],
  },
  { to: '/operators', label: 'Usuários', icon: 'operators', roles: ['ADMIN'] },
  { to: '/settings', label: 'Configurações', icon: 'settings', roles: ['ADMIN'] },
]

const SIDEBAR_KEY = 'tb_sidebar_compacta'

/** Lê a preferência de barra recolhida.
 *
 *  `localStorage` (e não `sessionStorage`, onde ficam os tokens): isto é
 *  preferência de tela, não sessão — quem recolheu a barra quer ela recolhida
 *  amanhã também. Navegador que bloqueia armazenamento cai no padrão em vez
 *  de derrubar a aplicação. */
function lerPreferencia(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

function Shell({ operator }: { operator: Operator }) {
  const navigate = useNavigate()
  const visible = NAV.filter((item) => item.roles.includes(operator.role))

  // Duas coisas diferentes, de propósito. No desktop a barra recolhe para dar
  // espaço à tabela e a preferência persiste. No celular ela é um menu que
  // abre por cima e sempre começa fechado — barra lateral fixa comeria a tela
  // inteira, e "recolhido" ali não é preferência, é o estado normal.
  const [compacta, setCompacta] = useState(lerPreferencia)
  const [menuAberto, setMenuAberto] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, compacta ? '1' : '0')
    } catch {
      /* modo privado ou armazenamento bloqueado: a preferência não persiste */
    }
  }, [compacta])

  // ESC fecha o menu do celular: quem abriu por engano não fica preso nele.
  useEffect(() => {
    if (!menuAberto) return
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuAberto(false)
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [menuAberto])

  return (
    <div className={`layout${compacta ? ' compacta' : ''}${menuAberto ? ' menu-aberto' : ''}`}>
      {/* Cabeçalho que só existe no celular: a barra lateral vira gaveta, e
          sem isto não sobraria nada clicável para abri-la. */}
      <header className="topbar">
        <button
          type="button"
          className="icon-button"
          aria-label={menuAberto ? 'fechar menu' : 'abrir menu'}
          aria-expanded={menuAberto}
          onClick={() => setMenuAberto((v) => !v)}
        >
          <Icon name="menu" />
        </button>
        <span className="brand-mark" aria-hidden="true">
          <Icon name="analytics" />
        </span>
        <strong>Tráfego · Telegram</strong>
        <ThemeToggle />
      </header>

      {/* Fundo que fecha a gaveta ao toque fora dela. Só existe no celular. */}
      <button
        type="button"
        className="menu-backdrop"
        tabIndex={-1}
        aria-hidden="true"
        onClick={() => setMenuAberto(false)}
      />

      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="analytics" />
          </span>
          <span className="brand-nome">Tráfego · Telegram</span>
          <button
            type="button"
            className="icon-button recolher"
            aria-label={compacta ? 'expandir barra lateral' : 'recolher barra lateral'}
            aria-expanded={!compacta}
            title={compacta ? 'expandir barra lateral' : 'recolher barra lateral'}
            onClick={() => setCompacta((v) => !v)}
          >
            <Icon name="chevronLeft" />
          </button>
        </div>

        <div className="identity" title={compacta ? operator.email : undefined}>
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
              // Recolhida, a barra mostra só o ícone: o rótulo passa a viver
              // no title, senão o item vira um símbolo sem nome.
              title={compacta ? item.label : undefined}
              onClick={() => setMenuAberto(false)}
            >
              <Icon name={item.icon} />
              <span className="nav-label">{item.label}</span>
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
            <Icon name="logout" />
            <span className="nav-label">Sair</span>
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
          <Route path="/settings" element={<Settings />} />
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
    return (
      <div style={{ padding: 32 }}>
        <Loading />
      </div>
    )
  }

  return <Shell operator={operator} />
}
