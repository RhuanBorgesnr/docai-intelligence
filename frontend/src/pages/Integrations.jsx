import React, { useState, useEffect } from 'react'
import api from '../services/api'

const STATUS_COLORS = {
  healthy: 'bg-green-500',
  inactive: 'bg-gray-500',
  circuit_open: 'bg-red-500',
}

const STATUS_LABELS = {
  healthy: 'Saudável',
  inactive: 'Inativo',
  circuit_open: 'Circuito Aberto',
}

const SYNC_STATUS_COLORS = {
  success: 'text-green-400',
  failed: 'text-red-400',
  pending: 'text-yellow-400',
  awaiting_approval: 'text-blue-400',
  in_progress: 'text-cyan-400',
  retrying: 'text-orange-400',
}

export default function Integrations() {
  const [connections, setConnections] = useState([])
  const [syncLogs, setSyncLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [testResult, setTestResult] = useState(null)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [connRes, logsRes, statsRes] = await Promise.all([
        api.get('/integrations/connections/'),
        api.get('/integrations/sync/logs/'),
        api.get('/integrations/sync/stats/'),
      ])
      setConnections(connRes.data)
      setSyncLogs(logsRes.data)
      setStats(statsRes.data)
    } catch (err) {
      console.error('Failed to load integrations data:', err)
    }
    setLoading(false)
  }

  async function handleTestConnection(connectionId) {
    setTestResult(null)
    try {
      const res = await api.post('/integrations/connections/test/', {
        connection_id: connectionId,
      })
      setTestResult({ id: connectionId, success: true })
    } catch (err) {
      setTestResult({
        id: connectionId,
        success: false,
        error: err.response?.data?.error_message || 'Falha na conexão',
      })
    }
  }

  async function handleApprove(syncLogId) {
    try {
      await api.post('/integrations/sync/approve/', { sync_log_id: syncLogId })
      loadData()
    } catch (err) {
      console.error('Approval failed:', err)
    }
  }

  if (loading) {
    return (
      <div className="p-6 text-gray-400 animate-pulse">
        Carregando integrações ERP...
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Integrações ERP</h1>
          <p className="text-gray-400 text-sm mt-1">
            Gerencie conexões com ERPs e acompanhe sincronizações
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
        >
          + Nova Conexão
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatsCard
            title="Conexões Ativas"
            value={stats.connections.active}
            subtitle={`${stats.connections.total} total`}
            color="blue"
          />
          <StatsCard
            title="Syncs (24h)"
            value={stats.last_24h.success}
            subtitle={`${stats.last_24h.total} total`}
            color="green"
          />
          <StatsCard
            title="Falhas (24h)"
            value={stats.last_24h.failed}
            subtitle={stats.last_24h.failed > 0 ? 'Atenção' : 'Tudo ok'}
            color={stats.last_24h.failed > 0 ? 'red' : 'green'}
          />
          <StatsCard
            title="Aguardando Aprovação"
            value={stats.last_24h.awaiting_approval}
            subtitle="Pendentes"
            color="yellow"
          />
        </div>
      )}

      {/* Add Connection Form */}
      {showAddForm && <AddConnectionForm onSuccess={() => { setShowAddForm(false); loadData() }} />}

      {/* Connections */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-3">Conexões</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {connections.map((conn) => (
            <ConnectionCard
              key={conn.id}
              connection={conn}
              onTest={() => handleTestConnection(conn.id)}
              testResult={testResult?.id === conn.id ? testResult : null}
            />
          ))}
          {connections.length === 0 && (
            <div className="col-span-full text-center text-gray-500 py-8">
              Nenhuma conexão ERP configurada. Clique em "+ Nova Conexão" para começar.
            </div>
          )}
        </div>
      </section>

      {/* Sync Logs */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-3">Últimas Sincronizações</h2>
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-700">
              <tr>
                <th className="px-4 py-2 text-left text-gray-300">Tipo</th>
                <th className="px-4 py-2 text-left text-gray-300">Conexão</th>
                <th className="px-4 py-2 text-left text-gray-300">Status</th>
                <th className="px-4 py-2 text-left text-gray-300">Duração</th>
                <th className="px-4 py-2 text-left text-gray-300">Data</th>
                <th className="px-4 py-2 text-left text-gray-300">Ações</th>
              </tr>
            </thead>
            <tbody>
              {syncLogs.map((log) => (
                <tr key={log.id} className="border-t border-gray-700 hover:bg-gray-750">
                  <td className="px-4 py-2 text-gray-200">{log.entity_type}</td>
                  <td className="px-4 py-2 text-gray-300">{log.connection_name}</td>
                  <td className={`px-4 py-2 font-medium ${SYNC_STATUS_COLORS[log.status] || 'text-gray-400'}`}>
                    {log.status}
                  </td>
                  <td className="px-4 py-2 text-gray-400">
                    {log.duration_ms ? `${log.duration_ms}ms` : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-400">
                    {new Date(log.created_at).toLocaleString('pt-BR')}
                  </td>
                  <td className="px-4 py-2">
                    {log.status === 'awaiting_approval' && (
                      <button
                        onClick={() => handleApprove(log.id)}
                        className="px-2 py-1 bg-green-600 hover:bg-green-700 text-white text-xs rounded"
                      >
                        Aprovar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {syncLogs.length === 0 && (
                <tr>
                  <td colSpan="6" className="px-4 py-6 text-center text-gray-500">
                    Nenhuma sincronização registrada ainda.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

// --- Sub-components ---

function StatsCard({ title, value, subtitle, color }) {
  const colors = {
    blue: 'border-blue-500',
    green: 'border-green-500',
    red: 'border-red-500',
    yellow: 'border-yellow-500',
  }
  return (
    <div className={`bg-gray-800 rounded-lg p-4 border-l-4 ${colors[color]}`}>
      <p className="text-gray-400 text-sm">{title}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-gray-500 text-xs">{subtitle}</p>
    </div>
  )
}

function ConnectionCard({ connection, onTest, testResult }) {
  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[connection.status]}`} />
          <h3 className="text-white font-medium">{connection.name}</h3>
        </div>
        <span className="text-xs text-gray-400 uppercase bg-gray-700 px-2 py-0.5 rounded">
          {connection.provider}
        </span>
      </div>

      <div className="text-sm text-gray-400 space-y-1 mb-3">
        <p>Status: <span className="text-gray-200">{STATUS_LABELS[connection.status]}</span></p>
        <p>Auto-sync: <span className="text-gray-200">{connection.auto_sync ? 'Sim' : 'Não'}</span></p>
        <p>Aprovação: <span className="text-gray-200">{connection.requires_approval ? 'Sim' : 'Não'}</span></p>
        {connection.last_sync_at && (
          <p>Último sync: <span className="text-gray-200">
            {new Date(connection.last_sync_at).toLocaleString('pt-BR')}
          </span></p>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={onTest}
          className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded transition-colors"
        >
          Testar Conexão
        </button>
      </div>

      {testResult && (
        <div className={`mt-2 text-xs p-2 rounded ${testResult.success ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
          {testResult.success ? '✓ Conexão OK' : `✗ ${testResult.error}`}
        </div>
      )}
    </div>
  )
}

function AddConnectionForm({ onSuccess }) {
  const [form, setForm] = useState({
    provider: 'omie',
    name: '',
    app_key: '',
    app_secret: '',
    requires_approval: true,
    auto_sync: false,
  })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await api.post('/integrations/connections/', form)
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao criar conexão')
    }
    setSubmitting(false)
  }

  return (
    <form onSubmit={handleSubmit} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h3 className="text-white font-semibold mb-4">Nova Conexão ERP</h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Provider</label>
          <select
            value={form.provider}
            onChange={(e) => setForm({ ...form, provider: e.target.value })}
            className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
          >
            <option value="omie">Omie</option>
            <option value="bling" disabled>Bling (em breve)</option>
            <option value="totvs" disabled>TOTVS (em breve)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Nome da Conexão</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Ex: Omie Produção"
            className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
            required
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">App Key</label>
          <input
            type="text"
            value={form.app_key}
            onChange={(e) => setForm({ ...form, app_key: e.target.value })}
            placeholder="Sua App Key do Omie"
            className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
            required
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">App Secret</label>
          <input
            type="password"
            value={form.app_secret}
            onChange={(e) => setForm({ ...form, app_secret: e.target.value })}
            placeholder="Sua App Secret do Omie"
            className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
            required
          />
        </div>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={form.requires_approval}
              onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
              className="rounded"
            />
            Requer aprovação
          </label>

          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={form.auto_sync}
              onChange={(e) => setForm({ ...form, auto_sync: e.target.checked })}
              className="rounded"
            />
            Auto-sync
          </label>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

      <div className="flex gap-3 mt-4">
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium disabled:opacity-50"
        >
          {submitting ? 'Criando...' : 'Criar Conexão'}
        </button>
        <button
          type="button"
          onClick={onSuccess}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
        >
          Cancelar
        </button>
      </div>
    </form>
  )
}
