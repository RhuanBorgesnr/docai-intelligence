/**
 * OpsCockpit — daily operations center.
 *
 * This is what you open every morning at /ops.
 * Shows: what happened today, what needs attention, costs, agent activity.
 * This is NOT a metrics-only page — it's an ACTION center.
 */
import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { commercial, executive } from '../services/commercial'

export default function OpsCockpit() {
  const [daily, setDaily] = useState(null)
  const [pipe, setPipe] = useState(null)
  const [brief, setBrief] = useState(null)
  const [sysStatus, setSysStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      executive.dailyOps().then(r => setDaily(r.data)),
      commercial.pipelineSummary().then(r => setPipe(r.data)),
      executive.briefing().then(r => setBrief(r.data)),
      executive.systemStatus().then(r => setSysStatus(r.data)),
    ]).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-8 text-gray-400">Carregando cockpit operacional…</div>

  const today = daily?.today || {}
  const costs = daily?.costs || {}
  const actions = daily?.actions_needed || []
  const activity = daily?.recent_activity || []
  const agentAct = daily?.agent_activity || []
  const alerts = brief?.alerts || []
  const priorities = brief?.top_priorities || []
  const k = pipe?.kpis || {}
  const greeting = new Date().getHours() < 12 ? 'Bom dia' : new Date().getHours() < 18 ? 'Boa tarde' : 'Boa noite'

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      {/* Morning greeting */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{greeting}! 👋</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
            {' · '}{today.new_leads || 0} leads novos hoje · {today.approvals_pending || 0} aprovações pendentes
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/ops/approvals" className="px-3 py-1.5 text-sm rounded-lg bg-violet-600 text-white hover:bg-violet-700 transition">
            ✅ Aprovações {today.approvals_pending ? `(${today.approvals_pending})` : ''}
          </Link>
          <Link to="/ops/leads" className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition">
            🎯 Ver leads
          </Link>
        </div>
      </div>

      {/* System status bar */}
      {sysStatus && (
        <div className={`rounded-lg px-4 py-2 flex items-center gap-4 text-xs ${
          sysStatus.llm?.ready ? 'bg-emerald-50 border border-emerald-200' : 'bg-red-50 border border-red-200'
        }`}>
          <StatusDot ok={sysStatus.llm?.ready} label={`LLM: ${sysStatus.llm?.provider} (${sysStatus.llm?.model || 'n/a'})`} />
          <StatusDot ok={sysStatus.database?.ok} label="Database" />
          <StatusDot ok={sysStatus.redis?.ok} label="Redis" />
          <StatusDot ok={!sysStatus.celery?.eager} label={`Celery: ${sysStatus.celery?.note}`} />
          <StatusDot ok={sysStatus.email?.is_real_smtp} label={`Email: ${sysStatus.email?.backend}`} />
          {!sysStatus.llm?.ready && (
            <span className="text-red-600 font-medium ml-auto">
              ⚠ {sysStatus.llm?.error || 'LLM não configurado'}
            </span>
          )}
        </div>
      )}

      {/* Actions needed — TOP PRIORITY */}
      {actions.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h2 className="text-sm font-bold text-red-800 mb-3">🚨 Ações necessárias AGORA</h2>
          <div className="space-y-2">
            {actions.map((a, i) => (
              <Link key={i} to={a.link || '/ops'} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-red-100 hover:border-red-300 transition">
                <span className="text-xl">{a.icon}</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">{a.title}</p>
                  <p className="text-xs text-gray-500">{a.action}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                  a.priority === 'high' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                }`}>{a.priority}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* KPIs row */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <Kpi label="Leads hoje" value={today.new_leads} accent />
        <Kpi label="Qualificados" value={today.qualified_today} />
        <Kpi label="Follow-ups enviados" value={today.followups_sent} />
        <Kpi label="Pendentes aprovação" value={today.approvals_pending} warn={today.approvals_pending > 0} />
        <Kpi label="Oport. ativas" value={today.active_opportunities || k.opportunities_active} />
        <Kpi label="Pipeline" value={fmt(k.pipeline_value_active)} />
        <Kpi label="Custo hoje" value={`$${(costs.today?.cost_usd || 0).toFixed(2)}`} />
        <Kpi label="Custo semana" value={`$${(costs.week?.cost_usd || 0).toFixed(2)}`} />
      </div>

      {/* Two-column layout: Priorities + Agent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Priorities */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">🎯 Prioridades do dia</h2>
          {priorities.length > 0 ? (
            <div className="space-y-2">
              {priorities.map((p, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-gray-50">
                  <span className="text-lg">{p.type === 'hot_lead' ? '🔥' : p.type === 'approval' ? '✅' : '📌'}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900">{p.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{p.detail}</p>
                    <p className="text-xs text-violet-600 mt-1">{p.action}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-4 text-center">Nenhuma prioridade — operação tranquila! 🟢</p>
          )}
        </div>

        {/* Agent activity today */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">🤖 Atividade dos agentes hoje</h2>
          {agentAct.length > 0 ? (
            <div className="space-y-2">
              {agentAct.map((a, i) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-gray-50">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-800">{a.agent_type}</p>
                    <div className="flex gap-3 text-xs text-gray-500 mt-0.5">
                      <span>{a.executions} exec</span>
                      <span className="text-green-600">{a.successes} ✓</span>
                      {a.failures > 0 && <span className="text-red-600">{a.failures} ✗</span>}
                      <span>{(a.tokens || 0).toLocaleString()} tokens</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-mono text-gray-700">${(a.cost || 0).toFixed(3)}</p>
                    <p className="text-[10px] text-gray-400">{(a.avg_latency || 0).toFixed(0)}ms avg</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-4 text-center">Nenhum agente executou ainda hoje.</p>
          )}
          <Link to="/ops/team" className="block text-center text-xs text-violet-600 hover:underline mt-3">
            Ver equipe completa →
          </Link>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-amber-800 mb-2">⚠ Alertas ({alerts.length})</h2>
          <ul className="space-y-1">
            {alerts.map((a, i) => (
              <li key={i} className="text-sm text-amber-700 flex items-start gap-2">
                <span className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                {a}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recent activity feed */}
      {activity.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">📋 Atividade recente (hoje)</h2>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {activity.map((e, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5 px-2 text-sm border-b border-gray-50 last:border-0">
                <span className="text-gray-400 text-xs w-14 shrink-0">
                  {new Date(e.at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                </span>
                <span className="text-gray-600 font-mono text-xs bg-gray-50 px-1.5 py-0.5 rounded">{e.action}</span>
                <span className="text-gray-400 text-xs truncate flex-1">{e.actor}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick nav */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <QuickLink to="/ops/leads" icon="🎯" label="Leads" desc="Captura e qualificação" />
        <QuickLink to="/ops/pipeline" icon="🔀" label="Pipeline" desc="Kanban de oportunidades" />
        <QuickLink to="/ops/theo" icon="🧠" label="Theo" desc="Briefing executivo + chat" />
        <QuickLink to="/ops/approvals" icon="✅" label="Aprovações" desc={`${today.approvals_pending || 0} pendentes`} />
        <QuickLink to="/ops/team" icon="👥" label="Equipe Digital" desc="Org chart + rotinas + KPIs" />
      </div>

      {/* Team snapshot */}
      {brief?.team && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">👥 Equipe Digital — {brief.team.active_agents}/{brief.team.total_agents} agentes ativos</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            {(brief.team.agents || []).map(a => (
              <Link
                key={a.agent_type}
                to="/ops/team"
                className={`p-2 rounded-lg border text-center hover:shadow-sm transition ${
                  a.status === 'active' ? 'bg-green-50 border-green-200' :
                  a.status === 'standby' ? 'bg-yellow-50 border-yellow-200' : 'bg-gray-50 border-gray-200'
                }`}
              >
                <div className="text-xl">{a.emoji}</div>
                <div className="text-xs font-medium text-gray-700 mt-1 truncate">{a.title.split('(')[0].trim()}</div>
                <div className="text-[10px] text-gray-400">{a.status}</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function fmt(v) {
  if (v == null) return '—'
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v)
}

function Kpi({ label, value, accent, warn }) {
  return (
    <div className={`rounded-lg p-3 border ${
      warn ? 'bg-red-50 border-red-200' :
      accent ? 'bg-violet-50 border-violet-200' : 'bg-white border-gray-200'
    }`}>
      <div className="text-[11px] text-gray-500 leading-tight">{label}</div>
      <div className={`text-xl font-semibold mt-1 ${warn ? 'text-red-600' : ''}`}>{value ?? '—'}</div>
    </div>
  )
}

function QuickLink({ to, icon, label, desc }) {
  return (
    <Link to={to} className="bg-white border border-gray-200 rounded-lg p-4 hover:border-violet-300 hover:shadow-sm transition group">
      <span className="text-2xl">{icon}</span>
      <p className="text-sm font-semibold mt-2 group-hover:text-violet-700 transition">{label}</p>
      <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
    </Link>
  )
}

function StatusDot({ ok, label }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-400'}`} />
      <span className={ok ? 'text-gray-600' : 'text-red-600'}>{label}</span>
    </span>
  )
}
