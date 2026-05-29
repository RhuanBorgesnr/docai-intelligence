/**
 * AgentDetail — slide-over panel with details of the selected agent.
 */
import React from 'react'

const STATUS_LABELS = {
  idle:    { text: 'Idle',    cls: 'bg-slate-200 text-slate-700', icon: '⏸' },
  active:  { text: 'Ativo',  cls: 'bg-green-100 text-green-800', icon: '▶' },
  warning: { text: 'Alerta', cls: 'bg-amber-100 text-amber-800', icon: '⚠' },
  error:   { text: 'Erro',   cls: 'bg-red-100 text-red-800',     icon: '✕' },
}

const ROLE_DESCRIPTIONS = {
  orchestrator: 'Coordena todos os agentes e toma decisões de routing',
  agent:        'Executa tarefas específicas do pipeline de vendas',
  operator:     'Processa documentos e análises automatizadas',
  gateway:      'Gerencia aprovações e autorizações humanas',
  service:      'Serviço de infraestrutura (notificações, memória, RAG)',
}

export default function AgentDetail({ agent, onClose }) {
  if (!agent) return null
  const sl = STATUS_LABELS[agent.status] || STATUS_LABELS.idle

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-80 sm:w-96 bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col animate-slide-in">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
          <div className="flex items-center gap-2">
            <span className="text-lg">{sl.icon}</span>
            <h2 className="text-sm font-bold text-gray-800">{agent.label}</h2>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full flex items-center justify-center text-gray-400 hover:bg-gray-200 hover:text-gray-700 transition"
            title="Fechar (Esc)"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {/* Status + Role */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${sl.cls}`}>{sl.text}</span>
              <span className="text-xs text-gray-500 capitalize">{agent.role}</span>
            </div>
            <p className="text-xs text-gray-400">{ROLE_DESCRIPTIONS[agent.role] || 'Agente do sistema'}</p>
          </div>

          {/* Metrics */}
          <div>
            <p className="text-xs font-semibold text-gray-600 mb-2">Métricas</p>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Na fila" value={agent.queue_size} icon="📋" />
              <Metric label="Erros" value={agent.error_count} icon="⚠" warn />
            </div>
          </div>

          {/* Connections */}
          <div>
            <p className="text-xs font-semibold text-gray-600 mb-2">Conexões</p>
            {(agent.connections || []).length === 0 ? (
              <p className="text-xs text-gray-400 italic">Sem conexões</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {(agent.connections || []).map((c) => (
                  <span key={c} className="px-2 py-1 bg-blue-50 border border-blue-100 rounded-lg text-[11px] text-blue-700 font-medium">
                    → {c}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Agent ID */}
          <div className="pt-3 border-t border-gray-100">
            <p className="text-[11px] text-gray-400">ID: {agent.id}</p>
          </div>
        </div>
      </div>
    </>
  )
}

function Metric({ label, value, icon, warn }) {
  const color = warn && value > 0 ? 'text-red-600' : 'text-gray-900'
  const bg = warn && value > 0 ? 'bg-red-50 border-red-100' : 'bg-gray-50 border-gray-100'
  return (
    <div className={`rounded-lg p-3 border ${bg}`}>
      <div className="flex items-center gap-1.5">
        <span className="text-sm">{icon}</span>
        <p className={`text-lg font-bold ${color}`}>{value ?? 0}</p>
      </div>
      <p className="text-[11px] text-gray-500 mt-0.5">{label}</p>
    </div>
  )
}
