/**
 * OpsAgentTeam — Digital Team dashboard at /ops/team.
 *
 * Shows every agent as a "team member" card with:
 * - Role, status, emoji
 * - Live KPIs
 * - Routines with manual trigger
 * - Responsibilities, deliverables, autonomy
 * - Approval gates
 * - Inter-agent communication graph
 * - Business impact
 *
 * Vision: DocAI = product, Theo/OpenClaw = digital company operating it.
 *
 * Sprint 4 / Phase 3.
 */
import React, { useState, useEffect } from 'react'
import { commercial } from '../services/commercial'

const STATUS_COLORS = {
  active: 'bg-green-100 text-green-800 border-green-300',
  standby: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  degraded: 'bg-red-100 text-red-800 border-red-300',
  disabled: 'bg-gray-100 text-gray-500 border-gray-300',
}

const STATUS_LABELS = {
  active: 'Ativo',
  standby: 'Standby',
  degraded: 'Degradado',
  disabled: 'Desativado',
}

export default function OpsAgentTeam() {
  const [team, setTeam] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [routineLoading, setRoutineLoading] = useState(null)
  const [routineResult, setRoutineResult] = useState(null)

  useEffect(() => {
    commercial.getAgentTeam()
      .then(r => setTeam(r.data?.team || []))
      .catch(() => setTeam([]))
      .finally(() => setLoading(false))
  }, [])

  const selectAgent = async (agentType) => {
    setSelected(agentType)
    setRoutineResult(null)
    try {
      const r = await commercial.getAgentDetail(agentType)
      setDetail(r.data)
    } catch {
      setDetail(null)
    }
  }

  const runRoutine = async (agentType, routineName) => {
    setRoutineLoading(routineName)
    setRoutineResult(null)
    try {
      const r = await commercial.runAgentRoutine(agentType, routineName)
      setRoutineResult({ routine: routineName, ...r.data })
    } catch (err) {
      setRoutineResult({ routine: routineName, error: err.response?.data?.error || 'Erro ao executar' })
    } finally {
      setRoutineLoading(null)
    }
  }

  if (loading) return <div className="p-6 text-gray-400">Carregando equipe digital…</div>

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Equipe Digital</h1>
        <p className="text-gray-500 mt-1">
          Theo/OpenClaw opera o DocAI como uma empresa digital. Cada agente é um membro da equipe com papel, responsabilidades, rotinas e métricas.
        </p>
      </div>

      {/* Team Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {team.map(agent => (
          <button
            key={agent.agent_type}
            onClick={() => selectAgent(agent.agent_type)}
            className={`text-left p-4 rounded-xl border-2 transition-all hover:shadow-md ${
              selected === agent.agent_type
                ? 'border-violet-500 bg-violet-50 shadow-md'
                : 'border-gray-200 bg-white hover:border-violet-300'
            }`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="text-2xl">{agent.emoji}</span>
              <div>
                <div className="font-semibold text-gray-900 text-sm">{agent.title}</div>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_COLORS[agent.status] || STATUS_COLORS.disabled}`}>
                  {STATUS_LABELS[agent.status] || agent.status}
                </span>
              </div>
            </div>
            <p className="text-xs text-gray-500 line-clamp-2">{agent.role_summary}</p>
            <div className="flex gap-3 mt-3 text-xs text-gray-400">
              <span title="Responsabilidades">📋 {agent.responsibilities_count}</span>
              <span title="Rotinas ativas">⏰ {agent.routines_enabled}/{agent.routines_count}</span>
              <span title="KPIs">📊 {agent.kpis_count}</span>
              {agent.approval_gates_count > 0 && (
                <span title="Portões de aprovação">🔒 {agent.approval_gates_count}</span>
              )}
            </div>
          </button>
        ))}
      </div>

      {/* Agent Detail Panel */}
      {detail && (
        <AgentDetailPanel
          detail={detail}
          onRunRoutine={runRoutine}
          routineLoading={routineLoading}
          routineResult={routineResult}
        />
      )}
    </div>
  )
}

function AgentDetailPanel({ detail, onRunRoutine, routineLoading, routineResult }) {
  const { charter, metrics } = detail
  if (!charter) return null

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm divide-y">
      {/* Header */}
      <div className="p-6">
        <div className="flex items-center gap-4">
          <span className="text-4xl">{charter.emoji}</span>
          <div>
            <h2 className="text-xl font-bold text-gray-900">{charter.title}</h2>
            <p className="text-gray-500">{charter.role_summary}</p>
            <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded-full border ${STATUS_COLORS[charter.status] || STATUS_COLORS.disabled}`}>
              {STATUS_LABELS[charter.status] || charter.status}
            </span>
          </div>
        </div>
        <div className="mt-4 p-3 bg-indigo-50 rounded-lg border border-indigo-200">
          <p className="text-sm text-indigo-800 font-medium">💼 Impacto no negócio</p>
          <p className="text-sm text-indigo-700 mt-1">{charter.business_impact}</p>
        </div>
      </div>

      {/* KPIs */}
      {metrics?.kpis && Object.keys(metrics.kpis).length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">📊 KPIs ao vivo</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {Object.entries(metrics.kpis).map(([key, val]) => {
              const kpiDef = charter.kpis?.find(k => k.name === key)
              return (
                <div key={key} className="bg-gray-50 rounded-lg p-3 border">
                  <div className="text-xs text-gray-500 truncate" title={kpiDef?.description || key}>
                    {kpiDef?.description || key.replace(/_/g, ' ')}
                  </div>
                  <div className="text-lg font-bold text-gray-900 mt-1">
                    {val === null ? '—' : typeof val === 'number' ? val.toLocaleString('pt-BR') : String(val)}
                    {kpiDef?.unit === 'percent' && val !== null ? '%' : ''}
                    {kpiDef?.unit === 'minutes' && val !== null ? ' min' : ''}
                  </div>
                  {kpiDef?.target != null && (
                    <div className="text-xs text-gray-400 mt-0.5">
                      Meta: {kpiDef.target}{kpiDef.unit === 'percent' ? '%' : ''}{kpiDef.unit === 'minutes' ? ' min' : ''}
                      {' '}{kpiDef.direction === 'higher' ? '↑' : '↓'}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Routines */}
      {charter.routines?.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">⏰ Rotinas</h3>
          <div className="space-y-2">
            {charter.routines.map(r => (
              <div key={r.name} className="flex items-center justify-between bg-gray-50 rounded-lg p-3 border">
                <div>
                  <div className="text-sm font-medium text-gray-900">{r.description}</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    Frequência: {r.frequency} · {r.enabled ? '✅ Ativa' : '⏸️ Pausada'}
                  </div>
                </div>
                <button
                  onClick={() => onRunRoutine(charter.agent_type, r.name)}
                  disabled={routineLoading === r.name}
                  className="px-3 py-1.5 text-xs font-medium bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 transition"
                >
                  {routineLoading === r.name ? '⏳' : '▶'} Executar
                </button>
              </div>
            ))}
          </div>
          {routineResult && (
            <div className={`mt-3 p-3 rounded-lg text-sm ${routineResult.error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
              <pre className="whitespace-pre-wrap text-xs">
                {JSON.stringify(routineResult.result || routineResult.error, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Responsibilities & Deliverables */}
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">📋 Responsabilidades</h3>
          <ul className="space-y-1">
            {charter.responsibilities?.map((r, i) => (
              <li key={i} className="text-sm text-gray-600 flex gap-2">
                <span className="text-gray-400">•</span> {r}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">📦 Entregáveis</h3>
          <ul className="space-y-1">
            {charter.deliverables?.map((d, i) => (
              <li key={i} className="text-sm text-gray-600 flex gap-2">
                <span className="text-green-500">✓</span> {d}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Autonomy & Approval Gates */}
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">🤖 Autonomia (faz sozinho)</h3>
          <ul className="space-y-1">
            {charter.autonomy?.map((a, i) => (
              <li key={i} className="text-sm text-gray-600 flex gap-2">
                <span className="text-blue-500">⚡</span> {a}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">🔒 Aprovação humana obrigatória</h3>
          {charter.approval_gates?.length > 0 ? (
            <ul className="space-y-2">
              {charter.approval_gates.map((g, i) => (
                <li key={i} className="bg-amber-50 rounded-lg p-2 border border-amber-200 text-sm">
                  <div className="font-medium text-amber-900">{g.description}</div>
                  <div className="text-xs text-amber-600 mt-0.5">
                    SLA: {g.sla_minutes} min · Aprovadores: {g.approver_roles.join(', ')}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 italic">Nenhuma — opera com autonomia total</p>
          )}
        </div>
      </div>

      {/* Communication */}
      {charter.communicates_with?.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">🔗 Comunica-se com</h3>
          <div className="flex flex-wrap gap-2">
            {charter.communicates_with.map(a => (
              <span key={a} className="px-3 py-1 bg-violet-100 text-violet-700 rounded-full text-xs font-medium border border-violet-200">
                {a}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
