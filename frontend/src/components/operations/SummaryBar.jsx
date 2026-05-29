/**
 * SummaryBar — compact KPI strip for the operations dashboard.
 */
import React from 'react'

const ITEMS = [
  { key: 'active_cases',         label: 'Cases ativos',      icon: '📂', color: 'text-blue-600',   tooltip: 'Número de cases em processamento no pipeline' },
  { key: 'pending_approvals',    label: 'Aprovações',        icon: '🔐', color: 'text-amber-600',  tooltip: 'Aprovações aguardando decisão humana' },
  { key: 'pending_notifications',label: 'Notificações',      icon: '📨', color: 'text-indigo-600', tooltip: 'Notificações pendentes de envio' },
  { key: 'dlq_size',             label: 'Dead-letter',       icon: '💀', color: 'text-red-600',    tooltip: 'Eventos que falharam e foram para a DLQ' },
]

export default function SummaryBar({ summary }) {
  if (!summary) return null
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {ITEMS.map((it) => {
        const value = summary[it.key] ?? 0
        const isWarn = it.key === 'dlq_size' && value > 0
        return (
          <div
            key={it.key}
            title={it.tooltip}
            className={`flex items-center gap-3 bg-white rounded-xl px-4 py-3 shadow-sm border transition-colors cursor-default ${
              isWarn ? 'border-red-200 bg-red-50' : 'border-gray-100 hover:border-gray-200'
            }`}
          >
            <span className="text-2xl">{it.icon}</span>
            <div>
              <p className={`text-xl font-bold ${isWarn ? 'text-red-600' : it.color}`}>{value}</p>
              <p className="text-[11px] text-gray-500">{it.label}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
