/**
 * Operations — visual agent-topology dashboard.
 *
 * Shows a 3D scene when WebGL is available, falls back to a
 * card grid when it's not (or when the user toggles the switch).
 *
 * Data comes from GET /api/orchestrator/dashboard/agents/
 * and auto-refreshes every 5 s.
 */
import React, { useState, useEffect, lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import useAgentStatus from '../hooks/useAgentStatus'
import { supportsWebGL } from '../utils/webgl'
import SummaryBar from '../components/operations/SummaryBar'
import AgentCardGrid from '../components/operations/AgentCardGrid'
import AgentDetail from '../components/operations/AgentDetail'

// Lazy-load the 3D scene so Three.js is never downloaded when not needed
const OperationsScene = lazy(() =>
  import('../components/operations/OperationsScene')
)

const STATUS_LEGEND = [
  { status: 'active',  label: 'Ativo',  color: 'bg-green-500' },
  { status: 'idle',    label: 'Idle',   color: 'bg-slate-400' },
  { status: 'warning', label: 'Alerta', color: 'bg-amber-500' },
  { status: 'error',   label: 'Erro',   color: 'bg-red-500'   },
]

export default function Operations() {
  const webglOk = supportsWebGL()
  const [view3D, setView3D] = useState(webglOk)
  const [selected, setSelected] = useState(null)
  const { data, loading, error, refetch } = useAgentStatus(5000)

  // Close detail panel on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') setSelected(null) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Loading state
  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
        <p className="text-sm text-gray-500">Carregando topologia de agentes…</p>
      </div>
    )
  }

  // Error state
  if (error && !data) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
          <span className="text-2xl">⚠️</span>
        </div>
        <p className="text-red-600 font-medium">Erro ao carregar dados</p>
        <p className="text-gray-500 text-sm max-w-md text-center">{error.message}</p>
        <button
          onClick={refetch}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition"
        >
          Tentar novamente
        </button>
      </div>
    )
  }

  const { agents = [], recent_events = [], summary = {} } = data || {}

  // Detect bottlenecks (agents with queue > 3 or errors > 0)
  const bottlenecks = agents.filter(a => (a.queue_size || 0) > 3 || (a.error_count || 0) > 0)

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Operações</h1>
          <p className="text-sm text-gray-500">Topologia de agentes em tempo real</p>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/ops/theo" className="text-sm px-3 py-1.5 rounded-lg bg-violet-100 hover:bg-violet-200 text-violet-700 transition font-medium">
            🧠 Jarvis
          </Link>
          <Link to="/ops" className="text-sm text-blue-600 hover:underline">← Cockpit</Link>

          {/* 3D / 2D toggle */}
          {webglOk && (
            <button
              onClick={() => setView3D(!view3D)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-sm text-gray-700 transition-colors"
              title={view3D ? 'Mudar para modo Cards' : 'Mudar para modo 3D'}
            >
              {view3D ? '📊 Modo Cards' : '🌐 Modo 3D'}
            </button>
          )}
        </div>
      </div>

      {/* KPI strip */}
      <SummaryBar summary={summary} />

      {/* Bottleneck alert */}
      {bottlenecks.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-start gap-3">
          <span className="text-lg mt-0.5">🔥</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">Gargalo detectado</p>
            <p className="text-xs text-amber-600 mt-0.5">
              {bottlenecks.map(a => a.label).join(', ')} — fila elevada ou erros ativos
            </p>
          </div>
        </div>
      )}

      {/* Status legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span className="font-medium text-gray-600">Legenda:</span>
        {STATUS_LEGEND.map(s => (
          <span key={s.status} className="flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 rounded-full ${s.color}`} />
            {s.label}
          </span>
        ))}
      </div>

      {/* Main visualisation */}
      {view3D ? (
        <Suspense fallback={
          <div className="h-[520px] rounded-xl bg-slate-900 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
          </div>
        }>
          <OperationsScene
            agents={agents}
            events={recent_events}
            onAgentClick={setSelected}
          />
        </Suspense>
      ) : (
        <AgentCardGrid agents={agents} onAgentClick={setSelected} />
      )}

      {/* Empty state for agents */}
      {agents.length === 0 && (
        <div className="bg-white border border-gray-100 rounded-xl p-12 text-center">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl">🤖</span>
          </div>
          <p className="text-gray-600 font-medium">Nenhum agente registrado</p>
          <p className="text-sm text-gray-400 mt-1">Os agentes aparecerão aqui quando o sistema estiver ativo</p>
        </div>
      )}

      {/* Recent events feed */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">Eventos recentes</h2>
          <span className="text-[11px] text-gray-400">{recent_events.length} evento(s)</span>
        </div>
        <div className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
          {recent_events.length === 0 && (
            <div className="flex flex-col items-center py-8 text-gray-400">
              <span className="text-2xl mb-2">📭</span>
              <p className="text-sm">Nenhum evento recente</p>
              <p className="text-[11px] mt-1">Eventos aparecerão aqui conforme os agentes processam cases</p>
            </div>
          )}
          {recent_events.map((evt, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-gray-50 transition-colors">
              <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
              <span className="font-medium text-gray-800 truncate">{evt.type}</span>
              <span className="text-gray-400 shrink-0">
                {evt.source} → {evt.target}
              </span>
              <span className="ml-auto text-[11px] text-gray-400 shrink-0">
                {new Date(evt.timestamp).toLocaleTimeString('pt-BR')}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Agent detail slide-over */}
      {selected && <AgentDetail agent={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
