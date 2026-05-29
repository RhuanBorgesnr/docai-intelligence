import React, { useEffect, useState } from 'react'
import { commercial } from '../services/commercial'

const STAGE_LABEL = {
  new: 'Novo',
  qualified: 'Qualificado',
  demo_scheduled: 'Demo agendada',
  demo_done: 'Demo realizada',
  proposal_sent: 'Proposta enviada',
  negotiation: 'Negociação',
  won: 'Ganhou',
  lost: 'Perdeu',
}

const ACTIVE_STAGES = ['new', 'qualified', 'demo_scheduled', 'demo_done', 'proposal_sent', 'negotiation']

function fmtMoney(v) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0)
}

export default function Pipeline() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = () => {
    setLoading(true)
    commercial
      .pipelineSummary()
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.message || 'Erro ao carregar pipeline'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const moveStage = async (id, stage) => {
    await commercial.moveOpportunity(id, stage)
    load()
  }

  if (loading) return <div className="p-6">Carregando pipeline…</div>
  if (error) return <div className="p-6 text-red-600">{error}</div>
  if (!data) return null

  const k = data.kpis
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Pipeline Comercial</h1>
        <button onClick={load} className="text-sm text-blue-600 hover:underline">Atualizar</button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Leads" value={k.leads_total} hint={`${k.leads_qualified} qualificados`} />
        <Kpi label="Oportunidades ativas" value={k.opportunities_active} hint={`${k.opportunities_won} ganhas`} />
        <Kpi label="Pipeline ativo" value={fmtMoney(k.pipeline_value_active)} hint={`${fmtMoney(k.pipeline_value_won)} ganho`} />
        <Kpi label="Score médio" value={Math.round(k.avg_lead_score || 0)} hint="0–100" />
      </div>

      {/* Kanban */}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {ACTIVE_STAGES.map((stage) => {
          const items = data.by_stage[stage] || []
          const value = data.stage_value[stage] || 0
          return (
            <div key={stage} className="min-w-[260px] bg-gray-50 rounded-lg p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-700">{STAGE_LABEL[stage]}</span>
                <span className="text-xs text-gray-500">{items.length} · {fmtMoney(value)}</span>
              </div>
              {items.length === 0 && (
                <div className="text-xs text-gray-400 italic py-4 text-center">vazio</div>
              )}
              {items.map((opp) => (
                <div key={opp.opportunity_id} className="bg-white rounded p-3 shadow-sm border border-gray-200">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium truncate">{opp.company_name || opp.lead_id}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700">{opp.score}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{fmtMoney(opp.estimated_value)}</div>
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {ACTIVE_STAGES.filter((s) => s !== stage).slice(0, 3).map((s) => (
                      <button
                        key={s}
                        onClick={() => moveStage(opp.opportunity_id, s)}
                        className="text-[10px] px-2 py-0.5 rounded bg-gray-100 hover:bg-gray-200 text-gray-700"
                      >
                        → {STAGE_LABEL[s]}
                      </button>
                    ))}
                    <button
                      onClick={() => moveStage(opp.opportunity_id, 'won')}
                      className="text-[10px] px-2 py-0.5 rounded bg-green-100 hover:bg-green-200 text-green-700"
                    >Ganhou</button>
                    <button
                      onClick={() => moveStage(opp.opportunity_id, 'lost')}
                      className="text-[10px] px-2 py-0.5 rounded bg-red-100 hover:bg-red-200 text-red-700"
                    >Perdeu</button>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Kpi({ label, value, hint }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {hint && <div className="text-xs text-gray-400 mt-1">{hint}</div>}
    </div>
  )
}
