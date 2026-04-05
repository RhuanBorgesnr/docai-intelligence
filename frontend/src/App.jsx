import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Chat from './pages/Chat'
import Indicators from './pages/Indicators'
import Charts from './pages/Charts'
import Compare from './pages/Compare'
import Clauses from './pages/Clauses'
import Settings from './pages/Settings'

export default function App() {
  return (
    <div className="app">
      <nav className="topnav">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-xl font-semibold text-gray-900">Plataforma</Link>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <Link to="/charts" className="text-sm text-gray-600 hover:text-gray-900">Gráficos</Link>
          <Link to="/compare" className="text-sm text-gray-600 hover:text-gray-900">Comparar</Link>
          <Link to="/upload" className="text-sm text-gray-600 hover:text-gray-900">Upload</Link>
          <Link to="/settings" className="text-sm text-gray-600 hover:text-gray-900">Configurações</Link>
          <Link to="/login" className="text-sm text-gray-600 hover:text-gray-900">Login</Link>
        </div>
      </nav>

      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/login" element={<Login />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/chat/:id" element={<Chat />} />
          <Route path="/indicators/:id" element={<Indicators />} />
          <Route path="/charts" element={<Charts />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/clauses/:id" element={<Clauses />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
