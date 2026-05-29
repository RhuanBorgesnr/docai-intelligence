/**
 * ClientLayout — navigation for external DocAI SaaS users.
 *
 * Shows only product features: Dashboard, Upload, Charts, Compare, Settings.
 * No access to operational / internal routes.
 */
import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { auth } from '../services/api'
import useDocumentStatus from '../hooks/useDocumentStatus'

export default function ClientLayout({ children }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const user = auth.getUser()
  const { connected, processingDocs } = useDocumentStatus()
  const processingCount = Object.keys(processingDocs).length

  return (
    <div className="app">
      <nav className="topnav">
        <div className="flex items-center gap-4">
          <Link to="/app" className="flex items-center gap-2">
            <img src="/icon.svg" alt="DocAI" className="w-8 h-8" />
            <span className="text-xl font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              DocAI
            </span>
          </Link>
          {/* Live connection indicator */}
          <div className="flex items-center gap-1.5" title={connected ? 'Conectado em tempo real' : 'Conectando...'}>
            <span className={`relative flex h-2 w-2 ${connected ? '' : 'opacity-50'}`}>
              {connected && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>}
              <span className={`relative inline-flex rounded-full h-2 w-2 ${connected ? 'bg-green-500' : 'bg-gray-400'}`}></span>
            </span>
            {processingCount > 0 && (
              <span className="text-xs text-blue-600 font-medium">{processingCount} processando</span>
            )}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <Link to="/app" className="text-sm text-gray-600 hover:text-gray-900">Dashboard</Link>
          <Link to="/app/upload" className="text-sm text-gray-600 hover:text-gray-900">Upload</Link>
          <Link to="/app/charts" className="text-sm text-gray-600 hover:text-gray-900">Gráficos</Link>
          <Link to="/app/compare" className="text-sm text-gray-600 hover:text-gray-900">Comparar</Link>
          <Link to="/app/settings" className="text-sm text-gray-600 hover:text-gray-900">Configurações</Link>

          <UserMenu user={user} show={showUserMenu} setShow={setShowUserMenu} settingsPath="/app/settings" />
        </div>
      </nav>
      <main>{children}</main>
    </div>
  )
}

export function UserMenu({ user, show, setShow, settingsPath = '/app/settings' }) {
  return (
    <div className="relative">
      <button
        onClick={() => setShow(!show)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors"
      >
        <div className="w-8 h-8 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center justify-center">
          <span className="text-white text-sm font-medium">
            {user?.username?.charAt(0)?.toUpperCase() || 'U'}
          </span>
        </div>
        <span className="text-sm text-gray-700 hidden sm:block">
          {user?.username || 'Usuário'}
        </span>
        <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {show && (
        <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg py-1 z-50">
          <div className="px-4 py-2 border-b border-gray-100">
            <p className="text-sm font-medium text-gray-900">{user?.username}</p>
            <p className="text-xs text-gray-500">Conectado</p>
          </div>
          <a
            href={settingsPath}
            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            onClick={() => setShow(false)}
          >
            Configurações
          </a>
          <button
            onClick={() => auth.logout()}
            className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
          >
            Sair
          </button>
        </div>
      )}
    </div>
  )
}
