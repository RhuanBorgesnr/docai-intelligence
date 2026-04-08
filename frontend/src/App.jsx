import React, { useEffect, useState } from 'react'
import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom'
import { auth } from './services/api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Chat from './pages/Chat'
import Indicators from './pages/Indicators'
import Charts from './pages/Charts'
import Compare from './pages/Compare'
import Clauses from './pages/Clauses'
import Settings from './pages/Settings'

// Protected Route Component
function ProtectedRoute({ children }) {
  const location = useLocation()

  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}

// Layout with Navigation
function Layout({ children }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const user = auth.getUser()

  const handleLogout = () => {
    auth.logout()
  }

  return (
    <div className="app">
      <nav className="topnav">
        <div className="flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2">
            <img src="/icon.svg" alt="Findocia" className="w-8 h-8" />
            <span className="text-xl font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              Findocia
            </span>
          </Link>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <Link to="/charts" className="text-sm text-gray-600 hover:text-gray-900">Gráficos</Link>
          <Link to="/compare" className="text-sm text-gray-600 hover:text-gray-900">Comparar</Link>
          <Link to="/upload" className="text-sm text-gray-600 hover:text-gray-900">Upload</Link>
          <Link to="/settings" className="text-sm text-gray-600 hover:text-gray-900">Configurações</Link>

          {/* User Menu */}
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
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

            {showUserMenu && (
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg py-1 z-50">
                <div className="px-4 py-2 border-b border-gray-100">
                  <p className="text-sm font-medium text-gray-900">{user?.username}</p>
                  <p className="text-xs text-gray-500">Conectado</p>
                </div>
                <Link
                  to="/settings"
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  onClick={() => setShowUserMenu(false)}
                >
                  Configurações
                </Link>
                <button
                  onClick={handleLogout}
                  className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  Sair
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      <main>{children}</main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      {/* Public route */}
      <Route path="/login" element={<Login />} />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout>
              <Dashboard />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/upload"
        element={
          <ProtectedRoute>
            <Layout>
              <Upload />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/chat/:id"
        element={
          <ProtectedRoute>
            <Layout>
              <Chat />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/indicators/:id"
        element={
          <ProtectedRoute>
            <Layout>
              <Indicators />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/charts"
        element={
          <ProtectedRoute>
            <Layout>
              <Charts />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/compare"
        element={
          <ProtectedRoute>
            <Layout>
              <Compare />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/clauses/:id"
        element={
          <ProtectedRoute>
            <Layout>
              <Clauses />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <Layout>
              <Settings />
            </Layout>
          </ProtectedRoute>
        }
      />

      {/* Redirect unknown routes */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
