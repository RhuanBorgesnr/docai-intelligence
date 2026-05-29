/**
 * LeadDetail — full operational view of a single lead.
 *
 * Lives at /ops/leads/:leadId.
 * Sections: header + score, documents (upload + list), DocAI demo trigger,
 * insights viewer, timeline (audit + events + score changes).
 */
import React, { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { commercial } from '../services/commercial'

const INSIGHT_ICONS = { opportunity: '💡', pain: '🩹', risk: '⚠️', value: '💎', compliance: '📋', generic: '📌' }
const INSIGHT_BG   = { opportunity: 'bg-blue-50 border-blue-200', pain: 'bg-red-50 border-red-200', risk: 'bg-amber-50 border-amber-200', value: 'bg-emerald-50 border-emerald-200', compliance: 'bg-violet-50 border-violet-200' }

export default function LeadDetail() {
  const { leadId } = useParams()
  const [lead, setLead] = useState(null)
  const [docs, setDocs] = useState([])
  const [insights, setInsights] = useState([])
  const [timeline, setTimeline] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('insights')

  const load = useCallback(() => {
    setLoading(true)
    Promise.allSettled([
      commercial.getLead(leadId).then(r => setLead(r.data)),
      commercial.listDocuments(leadId).then(r => setDocs(r.data.documents || [])),
      commercial.getInsights(leadId).then(r => setInsights(r.data.insights || [])),
      commercial.getTimeline(leadId).then(r => setTimeline(r.data.events || [])),
    ]).finally(() => setLoading(false))
  }, [leadId])

  useEffect(load, [load])

  if (loading && !lead) return <div className="p-6 text-gray-400">Carregando lead…</div>
  if (!lead) return <div className="p-6 text-red-500">Lead não encontrado.</div>

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Breadcrumb */}
      <div className="text-xs text-gray-400">
        <Link to="/ops/leads" className="hover:text-violet-600">Leads</Link> / {lead.company_name || lead.lead_id}
      </div>

      {/* Header */}
      <LeadHeader lead={lead} onRefresh={load} />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {[
          { id: 'insights', label: 'Insights DocAI', count: insights.length },
          { id: 'docs', label: 'Documentos', count: docs.length },
          { id: 'timeline', label: 'Timeline', count: timeline.length },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition ${
              tab === t.id ? 'border-violet-600 text-violet-700' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}{t.count > 0 ? ` (${t.count})` : ''}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'insights' && <InsightsTab insights={insights} lead={lead} docs={docs} onRefresh={load} />}
      {tab === 'docs' && <DocumentsTab leadId={leadId} docs={docs} onRefresh={load} />}
      {tab === 'timeline' && <TimelineTab events={timeline} />}
    </div>
  )
}

/* ── Header with score + actions ──────────────────────────────────────────── */

function LeadHeader({ lead, onRefresh }) {
  const [busy, setBusy] = useState(null)
  const [lastAction, setLastAction] = useState(null)

  const qualify = async () => {
    setBusy('q')
    try {
      const r = await commercial.qualifyLead(lead.lead_id)
      setLastAction({ type: 'qualify', ...r.data })
      onRefresh()
    } catch (e) {
      setLastAction({ type: 'qualify', error: e.response?.data?.detail || e.message })
    } finally { setBusy(null) }
  }
  const followup = async () => {
    setBusy('f')
    try {
      const r = await commercial.draftFollowup(lead.lead_id, { channel: 'email' })
      setLastAction({ type: 'followup', ...r.data })
      onRefresh()
    } catch (e) {
      setLastAction({ type: 'followup', error: e.response?.data?.detail || e.message })
    } finally { setBusy(null) }
  }
  const scheduleDemo = async () => { setBusy('d'); try { await commercial.scheduleDemo(lead.lead_id); onRefresh() } finally { setBusy(null) } }

  // WhatsApp deep link
  const waPhone = lead.contact_phone ? lead.contact_phone.replace(/\D/g, '') : ''
  const waLink = waPhone
    ? `https://wa.me/${waPhone.startsWith('55') ? waPhone : '55' + waPhone}?text=${encodeURIComponent(`Olá ${lead.contact_name || ''}! Sou da equipe DocAI.`)}`
    : null

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-start gap-5">
      {/* Score circle */}
      <div className={`w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold shrink-0 ${
        lead.score >= 80 ? 'bg-green-100 text-green-700' :
        lead.score >= 60 ? 'bg-emerald-100 text-emerald-700' :
        lead.score >= 40 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'
      }`}>{lead.score}</div>

      <div className="flex-1 min-w-0">
        <h1 className="text-xl font-bold text-gray-900">{lead.company_name || '(sem empresa)'}</h1>
        <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
          <span>{lead.contact_email || lead.contact_name}</span>
          {lead.industry && <span className="px-2 py-0.5 rounded bg-gray-100 text-xs">{lead.industry}</span>}
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
            lead.status === 'qualified' ? 'bg-emerald-100 text-emerald-700' :
            lead.status === 'converted' ? 'bg-violet-100 text-violet-700' :
            lead.status === 'disqualified' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700'
          }`}>{lead.status}</span>
        </div>
        {lead.company_size && <div className="text-xs text-gray-400 mt-1">Porte: {lead.company_size} · País: {lead.country}</div>}
      </div>

      <div className="flex gap-2 shrink-0">
        <button onClick={qualify} disabled={!!busy} className="px-3 py-1.5 text-sm rounded bg-amber-100 hover:bg-amber-200 text-amber-800 disabled:opacity-50">
          {busy === 'q' ? '…' : 'Re-qualificar'}
        </button>
        <button onClick={followup} disabled={!!busy || !lead.contact_email} className="px-3 py-1.5 text-sm rounded bg-blue-100 hover:bg-blue-200 text-blue-800 disabled:opacity-50">
          {busy === 'f' ? '…' : 'Follow-up'}
        </button>
        <button onClick={scheduleDemo} disabled={!!busy} className="px-3 py-1.5 text-sm rounded bg-violet-100 hover:bg-violet-200 text-violet-800 disabled:opacity-50">
          {busy === 'd' ? '…' : '📅 Agendar Demo'}
        </button>
        {waLink && (
          <a href={waLink} target="_blank" rel="noopener noreferrer" className="px-3 py-1.5 text-sm rounded bg-green-100 hover:bg-green-200 text-green-800 inline-flex items-center gap-1">
            💬 WhatsApp
          </a>
        )}
      </div>

      {/* Agent execution feedback */}
      {lastAction && (
        <div className={`mt-3 p-3 rounded-lg text-sm ${lastAction.error ? 'bg-red-50 border border-red-200' : 'bg-emerald-50 border border-emerald-200'}`}>
          {lastAction.error ? (
            <p className="text-red-700">❌ Erro: {lastAction.error}</p>
          ) : lastAction.type === 'qualify' ? (
            <div className="text-emerald-800">
              <p>✅ <strong>{lastAction.qualified ? 'Qualificado' : 'Desqualificado'}</strong> — confiança {(lastAction.confidence * 100).toFixed(0)}% — {lastAction.reason}</p>
              {lastAction.agent && (
                <p className="text-xs text-gray-500 mt-1">
                  Provider: <strong>{lastAction.agent.provider}</strong> · Status: {lastAction.agent.status} · {lastAction.agent.tokens} tokens · {lastAction.agent.latency_ms}ms
                </p>
              )}
            </div>
          ) : lastAction.type === 'followup' ? (
            <p className="text-emerald-800">✅ Follow-up criado — aguardando aprovação em <a href="/ops/approvals" className="underline font-medium">/ops/approvals</a></p>
          ) : null}
        </div>
      )}
    </div>
  )
}

/* ── Insights tab ─────────────────────────────────────────────────────────── */

function InsightsTab({ insights, lead, docs, onRefresh }) {
  const [running, setRunning] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState(docs[0]?.document_id || '')

  const runDemo = async () => {
    if (!selectedDoc) return
    setRunning(true)
    try {
      await commercial.runDocaiDemo(lead.lead_id, selectedDoc)
      onRefresh()
    } finally { setRunning(false) }
  }

  return (
    <div className="space-y-4">
      {/* Run demo */}
      <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 flex items-center gap-3 flex-wrap">
        <span className="text-lg">🚀</span>
        <span className="text-sm font-medium text-violet-800">Rodar demo DocAI</span>
        <select
          value={selectedDoc}
          onChange={e => setSelectedDoc(e.target.value)}
          className="border rounded px-2 py-1 text-sm flex-1 min-w-[200px]"
        >
          <option value="">Selecione um documento…</option>
          {docs.map(d => <option key={d.document_id} value={d.document_id}>{d.title} ({d.document_type})</option>)}
        </select>
        <button
          onClick={runDemo}
          disabled={running || !selectedDoc}
          className="px-4 py-1.5 rounded bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 disabled:opacity-50"
        >
          {running ? 'Analisando…' : 'Gerar insights'}
        </button>
      </div>

      {/* Empty state */}
      {insights.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <span className="text-4xl block mb-3">📊</span>
          <p>Nenhum insight gerado ainda.</p>
          <p className="text-xs mt-1">Faça upload de um documento e clique em "Gerar insights".</p>
        </div>
      )}

      {/* Insight cards (most recent analysis first) */}
      {insights.map((analysis, idx) => (
        <div key={idx} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <div>
              <span className="text-sm font-semibold text-gray-700">Análise #{insights.length - idx}</span>
              <span className="text-xs text-gray-400 ml-3">{analysis.generated_at}</span>
            </div>
            {analysis.rag_sources?.length > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded bg-blue-50 text-blue-600">
                RAG: {analysis.rag_sources.length} fontes
              </span>
            )}
          </div>

          {/* Summary */}
          {analysis.summary && (
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-sm font-medium text-gray-700 mb-1">📝 Resumo executivo</p>
              <p className="text-sm text-gray-600 whitespace-pre-line">{analysis.summary}</p>
            </div>
          )}

          {/* Insights */}
          <div className="px-4 py-3 space-y-2">
            {(analysis.insights || []).map((ins, i) => (
              <div key={i} className={`border rounded-lg p-3 ${INSIGHT_BG[ins.type] || 'bg-gray-50 border-gray-200'}`}>
                <div className="flex items-start gap-2">
                  <span className="text-base mt-0.5">{INSIGHT_ICONS[ins.type] || '📌'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-gray-800">{ins.title}</span>
                      {ins.score != null && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                          ins.score >= 80 ? 'bg-green-200 text-green-800' :
                          ins.score >= 60 ? 'bg-blue-200 text-blue-800' : 'bg-gray-200 text-gray-700'
                        }`}>Score {ins.score}</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-600 mt-1"><strong>Evidência:</strong> {ins.evidence}</p>
                    <p className="text-xs text-violet-700 mt-1"><strong>Ação:</strong> {ins.action}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Automations */}
          {analysis.automations?.length > 0 && (
            <div className="px-4 py-3 border-t border-gray-100">
              <p className="text-xs font-medium text-gray-500 mb-1">🤖 Automações sugeridas</p>
              <div className="flex flex-wrap gap-1.5">
                {analysis.automations.map((a, i) => (
                  <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{a}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ── Documents tab ────────────────────────────────────────────────────────── */

function DocumentsTab({ leadId, docs, onRefresh }) {
  const [uploading, setUploading] = useState(false)

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await commercial.uploadDocument(leadId, file, file.name)
      onRefresh()
    } finally { setUploading(false); e.target.value = '' }
  }

  return (
    <div className="space-y-4">
      {/* Upload */}
      <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-xl p-6 text-center">
        <input type="file" id="doc-upload" className="hidden" onChange={handleUpload} accept=".pdf,.txt,.csv,.xlsx,.docx" />
        <label htmlFor="doc-upload" className="cursor-pointer">
          <span className="text-3xl block mb-2">📄</span>
          <p className="text-sm font-medium text-gray-700">{uploading ? 'Enviando…' : 'Clique para enviar documento'}</p>
          <p className="text-xs text-gray-400 mt-1">PDF, TXT, CSV, Excel, Word</p>
        </label>
      </div>

      {/* List */}
      {docs.length === 0 && (
        <p className="text-center text-gray-400 text-sm py-6">Nenhum documento associado.</p>
      )}
      {docs.map(d => (
        <div key={d.document_id} className="bg-white border border-gray-200 rounded-lg p-4 flex items-center gap-3">
          <span className="text-xl">📄</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800 truncate">{d.title}</p>
            <p className="text-xs text-gray-400">{d.document_type} · {d.processing_status} · {d.created_at?.split('T')[0]}</p>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded ${
            d.processing_status === 'completed' ? 'bg-green-100 text-green-700' :
            d.processing_status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
          }`}>{d.processing_status}</span>
        </div>
      ))}
    </div>
  )
}

/* ── Timeline tab ─────────────────────────────────────────────────────────── */

function TimelineTab({ events }) {
  if (events.length === 0) {
    return <p className="text-center text-gray-400 text-sm py-12">Nenhum evento registrado.</p>
  }

  const icon = (type) => {
    if (type === 'event') return '⚡'
    if (type === 'audit') return '📋'
    if (type === 'score_change') return '📈'
    return '·'
  }

  return (
    <div className="space-y-0">
      {events.map((evt, i) => (
        <div key={i} className="flex gap-3 py-2 border-b border-gray-50 last:border-0">
          <span className="mt-0.5 text-sm">{icon(evt.type)}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium text-gray-700">
                {evt.type === 'event' && evt.event_type}
                {evt.type === 'audit' && evt.action}
                {evt.type === 'score_change' && `Score: ${evt.score_before} → ${evt.score_after}`}
              </span>
              <span className="text-[10px] text-gray-400">{formatTs(evt.timestamp)}</span>
            </div>
            {evt.type === 'event' && evt.source && <p className="text-xs text-gray-400">source: {evt.source}</p>}
            {evt.type === 'audit' && evt.actor_id && <p className="text-xs text-gray-400">{evt.actor_type}: {evt.actor_id}</p>}
            {evt.type === 'score_change' && evt.reason && <p className="text-xs text-gray-500">{evt.reason}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

function formatTs(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) } catch { return iso }
}
