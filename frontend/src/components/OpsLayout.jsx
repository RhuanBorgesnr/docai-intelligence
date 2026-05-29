/**
 * OpsLayout — internal operations cockpit for the DocAI company.
 *
 * Visible only to staff/ops users (`is_staff` flag in JWT).
 * Contains: Leads, Pipeline, Theo (Jarvis), Operations, Approvals, Agents.
 *
 * Visual differentiation: dark sidebar with violet accent (vs. the clean
 * white top-nav of the client product).
 */
import React, { useState, useEffect } from 'react'
import { Link, NavLink, Navigate, useLocation } from 'react-router-dom'
import { auth } from '../services/api'
import api from '../services/api'

const NAV_ITEMS = [
  { to: '/ops',           icon: '📊', label: 'Cockpit' },
  { to: '/ops/leads',     icon: '🎯', label: 'Leads' },
  { to: '/ops/pipeline',  icon: '🔀', label: 'Pipeline' },
  { to: '/ops/theo',      icon: '🧠', label: 'Theo' },
  { to: '/ops/operations',icon: '⚙️', label: 'Operações' },
  { to: '/ops/approvals', icon: '✅', label: 'Aprovações' },
  { to: '/ops/team',      icon: '👥', label: 'Equipe Digital' },
]

/**
 * Guard: only allow staff users into /ops/*.
 * Reads `is_staff` from the JWT payload. Falls back to `/app` for non-staff.
 */
export function OpsGuard({ children }) {
  const user = auth.getUser()
  const location = useLocation()

  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // JWT should contain is_staff (set via Django SimpleJWT CUSTOM_CLAIMS or token serializer).
  // Fallback: if the claim isn't present, allow access (dev mode) — the backend
  // still enforces IsAdminUser on the API side.
  if (user && user.is_staff === false) {
    return <Navigate to="/app" replace />
  }

  return children
}

export default function OpsLayout({ children }) {
  const [collapsed, setCollapsed] = useState(false)
  const user = auth.getUser()

  // Poll pending approvals for badge
  const [pendingCount, setPendingCount] = useState(0)
  useEffect(() => {
    const fetchCount = () => {
      api.get('/approvals/count/')
        .then(r => setPendingCount(r.data?.pending || 0))
        .catch(() => {})
    }
    fetchCount()
    const interval = setInterval(fetchCount, 30_000)  // poll every 30s
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className={`${collapsed ? 'w-16' : 'w-56'} bg-gray-900 text-gray-300 flex flex-col transition-all duration-200`}>
        {/* Brand */}
        <div className="flex items-center gap-2 px-4 h-14 border-b border-gray-800">
          <button onClick={() => setCollapsed(!collapsed)} className="text-violet-400 hover:text-white transition">
            {collapsed ? '☰' : '✕'}
          </button>
          {!collapsed && (
            <span className="text-sm font-bold bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent tracking-wide">
              DocAI Ops
            </span>
          )}
        </div>

        {/* Nav links */}
        <nav className="flex-1 py-3 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/ops'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-violet-600/20 text-white border-l-2 border-violet-400'
                    : 'hover:bg-gray-800 hover:text-white border-l-2 border-transparent'
                }`
              }
            >
              <span className="text-base">{item.icon}</span>
              {!collapsed && (
                <span className="flex-1">{item.label}</span>
              )}
              {/* Badge for pending approvals */}
              {item.to === '/ops/approvals' && pendingCount > 0 && (
                <span className="ml-auto bg-red-500 text-white text-[10px] font-bold min-w-[18px] h-[18px] flex items-center justify-center rounded-full">
                  {pendingCount > 99 ? '99+' : pendingCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User footer */}
        <div className="border-t border-gray-800 px-4 py-3 flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-gradient-to-r from-violet-500 to-indigo-500 flex items-center justify-center shrink-0">
            <span className="text-white text-xs font-medium">
              {user?.username?.charAt(0)?.toUpperCase() || 'O'}
            </span>
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-gray-200 truncate">{user?.username || 'Ops'}</p>
              <button onClick={() => auth.logout()} className="text-[10px] text-red-400 hover:text-red-300">Sair</button>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
          <div className="text-sm text-gray-500">
            <Link to="/app" className="hover:text-blue-600 transition">← Produto DocAI</Link>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-400">
            <span className="px-2 py-0.5 rounded bg-violet-100 text-violet-700 font-medium">Área interna</span>
            <span>{new Date().toLocaleDateString('pt-BR')}</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
