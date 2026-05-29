import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { commercial } from '../services/commercial'

const STATUS_BADGE = {
  new: 'bg-gray-100 text-gray-700',
  qualifying: 'bg-amber-100 text-amber-700',
  qualified: 'bg-emerald-100 text-emerald-700',
  disqualified: 'bg-red-100 text-red-700',
  nurturing: 'bg-blue-100 text-blue-700',
  converted: 'bg-violet-100 text-violet-700',
}

export default function Leads() {
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [busyLead, setBusyLead] = useState(null)
  const [showIngest, setShowIngest] = useState(false)

  const load = () => {
    setLoading(true)
    commercial
      .listLeads(filter ? { status: filter } : {})
      .then((r) => setLeads(r.data.results || r.data))
      .finally(() => setLoading(false))
  }
  useEffect(load, [filter])

  const requalify = async (leadId) => {
    setBusyLead(leadId)
    try { await commercial.qualifyLead(leadId); load() } finally { setBusyLead(null) }
  }
  const followup = async (leadId) => {
    setBusyLead(leadId)
    try { await commercial.draftFollowup(leadId, { channel: 'email' }); load() } finally { setBusyLead(null) }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Leads</h1>
        <div className="flex items-center gap-2">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="border rounded px-2 py-1 text-sm">
            <option value="">Todos</option>
            <option value="new">Novos</option>
            <option value="qualifying">Em qualificação</option>
            <option value="qualified">Qualificados</option>
            <option value="converted">Convertidos</option>
            <option value="disqualified">Desqualificados</option>
          </select>
          <button onClick={() => setShowIngest(!showIngest)} className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm">
            + Lead manual
          </button>
        </div>
      </div>

      {showIngest && <IngestForm onSaved={() => { setShowIngest(false); load() }} />}

      {loading && <div>Carregando…</div>}

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="p-3">Lead</th>
              <th className="p-3">Score</th>
              <th className="p-3">Status</th>
              <th className="p-3">Fonte</th>
              <th className="p-3">Indústria</th>
              <th className="p-3">Ações</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((l) => (
              <tr key={l.lead_id} className="border-t border-gray-100">
                <td className="p-3">
                  <Link to={`/ops/leads/${l.lead_id}`} className="hover:text-violet-700 transition">
                    <div className="font-medium">{l.company_name || '(sem empresa)'}</div>
                    <div className="text-xs text-gray-500">{l.contact_email || l.contact_name || l.lead_id}</div>
                  </Link>
                </td>
                <td className="p-3"><ScoreBadge score={l.score} /></td>
                <td className="p-3">
                  <span className={`text-xs px-2 py-0.5 rounded ${STATUS_BADGE[l.status] || 'bg-gray-100'}`}>{l.status}</span>
                </td>
                <td className="p-3 text-xs text-gray-600">{l.source}</td>
                <td className="p-3 text-xs text-gray-600">{l.industry || '—'}</td>
                <td className="p-3">
                  <div className="flex gap-1 flex-wrap">
                    <button
                      onClick={() => requalify(l.lead_id)}
                      disabled={busyLead === l.lead_id}
                      className="text-xs px-2 py-1 rounded bg-amber-100 hover:bg-amber-200 text-amber-800"
                    >Re-qualificar</button>
                    <button
                      onClick={() => followup(l.lead_id)}
                      disabled={busyLead === l.lead_id || !l.contact_email}
                      className="text-xs px-2 py-1 rounded bg-blue-100 hover:bg-blue-200 text-blue-800 disabled:opacity-50"
                    >Follow-up</button>
                  </div>
                </td>
              </tr>
            ))}
            {leads.length === 0 && !loading && (
              <tr><td colSpan={6} className="p-6 text-center text-gray-400">Nenhum lead encontrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ScoreBadge({ score }) {
  const tone =
    score >= 80 ? 'bg-green-600 text-white' :
    score >= 60 ? 'bg-emerald-100 text-emerald-700' :
    score >= 40 ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-600'
  return <span className={`text-xs px-2 py-0.5 rounded font-medium ${tone}`}>{score}</span>
}

function IngestForm({ onSaved }) {
  const [form, setForm] = useState({
    source: 'manual', contact_name: '', contact_email: '',
    company_name: '', industry: '', company_size: '', country: 'BR',
    consent_given: true,
  })
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try { await commercial.ingestLead(form); onSaved() } finally { setBusy(false) }
  }
  const f = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  return (
    <form onSubmit={submit} className="bg-gray-50 border border-gray-200 rounded p-4 space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
        <input className="border rounded px-2 py-1" placeholder="Empresa" value={form.company_name} onChange={f('company_name')} />
        <input className="border rounded px-2 py-1" placeholder="Email" value={form.contact_email} onChange={f('contact_email')} />
        <input className="border rounded px-2 py-1" placeholder="Nome contato" value={form.contact_name} onChange={f('contact_name')} />
        <input className="border rounded px-2 py-1" placeholder="Indústria" value={form.industry} onChange={f('industry')} />
        <input className="border rounded px-2 py-1" placeholder="Tamanho (ex: 51-200)" value={form.company_size} onChange={f('company_size')} />
        <select className="border rounded px-2 py-1" value={form.source} onChange={f('source')}>
          {['manual','landing_page','inbound_form','referral','outbound','linkedin','event','partner'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <button disabled={busy} className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50">
        {busy ? 'Enviando…' : 'Capturar lead'}
      </button>
    </form>
  )
}
