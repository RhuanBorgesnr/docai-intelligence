/**
 * AgentCardGrid — 2D fallback for the operations view.
 *
 * Renders each agent as a coloured card with queue/error badges,
 * working without WebGL.
 */
import React from 'react'

const STATUS_STYLES = {
  idle:    { bg: 'bg-slate-100',  border: 'border-slate-300',  dot: 'bg-slate-400'  },
  active:  { bg: 'bg-green-50',   border: 'border-green-400',  dot: 'bg-green-500'  },
  warning: { bg: 'bg-amber-50',   border: 'border-amber-400',  dot: 'bg-amber-500'  },
  error:   { bg: 'bg-red-50',     border: 'border-red-400',    dot: 'bg-red-500'    },
}

const ROLE_ICONS = {
  orchestrator: '🧠',
  agent:        '🤖',
  operator:     '⚙️',
  gateway:      '🔐',
  service:      '📡',
}

export default function AgentCardGrid({ agents, onAgentClick }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
      {agents.map((agent) => {
        const s = STATUS_STYLES[agent.status] || STATUS_STYLES.idle
        return (
          <button
            key={agent.id}
            onClick={() => onAgentClick?.(agent)}
            className={`${s.bg} ${s.border} border-2 rounded-xl p-4 text-left transition-all hover:shadow-lg hover:scale-[1.02] focus:outline-none focus:ring-2 focus:ring-blue-400`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-2xl">{ROLE_ICONS[agent.role] || '🔹'}</span>
              <span className={`w-3 h-3 rounded-full ${s.dot} ${agent.status === 'active' ? 'animate-pulse' : ''}`} />
            </div>
            <h3 className="text-sm font-semibold text-gray-800 mb-1">{agent.label}</h3>
            <p className="text-[11px] text-gray-500 capitalize mb-3">{agent.role}</p>

            <div className="flex items-center gap-2 text-xs">
              {agent.queue_size > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
                  📋 {agent.queue_size}
                </span>
              )}
              {agent.error_count > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-medium">
                  ⚠ {agent.error_count}
                </span>
              )}
              {agent.queue_size === 0 && agent.error_count === 0 && (
                <span className="text-gray-400 italic">sem fila</span>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
