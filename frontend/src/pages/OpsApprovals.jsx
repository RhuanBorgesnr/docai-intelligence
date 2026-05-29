/**
 * OpsApprovals — Approval queue at /ops/approvals.
 *
 * The human control layer: every sensitive action (follow-up, proposal,
 * discount, etc.) passes through here before being executed.
 *
 * Shows pending approvals sorted by deadline, with one-click approve/reject
 * and optional comment.
 *
 * Sprint 4 / Phase 4A.
 */
import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const STATUS_STYLES = {
  pending:   'bg-amber-100 text-amber-800 border-amber-300',
  escalated: 'bg-red-100 text-red-800 border-red-300',
  approved:  'bg-green-100 text-green-700 border-green-300',
  rejected:  'bg-gray-100 text-gray-600 border-gray-300',
  expired:   'bg-gray-100 text-gray-400 border-gray-200',
  changes_requested: 'bg-blue-100 text-blue-700 border-blue-300',
}

const STATUS_LABELS = {
  pending: 'Pendente',
  escalated: 'Escalado',
  approved: 'Aprovado',
  rejected: 'Rejeitado',
  expired: 'Expirado',
  changes_requested: 'Mudanças solicitadas',
}

export default function OpsApprovals() {
  const [approvals, setApprovals] = useState([])
  const [filter, setFilter] = useState('pending')
  const [loading, setLoading] = useState(true)
  const [deciding, setDeciding] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [comment, setComment] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    api.get('/approvals/', { params: { status: filter } })
      .then(r => setApprovals(r.data?.approvals || []))
      .catch(() => setApprovals([]))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(load, [load])

  const decide = async (approvalId, decision) => {
    setDeciding(approvalId)
    try {
      await api.post(`/approvals/${approvalId}/decide/`, { decision, comment })
      setComment('')
      setExpanded(null)
      load()
    } catch (err) {
      alert(err.response?.data?.error || 'Erro ao decidir')
    } finally {
      setDeciding(null)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Aprovações</h1>
          <p className="text-sm text-gray-500 mt-1">Controle humano sobre decisões dos agentes</p>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
          {[
            { id: 'pending', label: 'Pendentes' },
            { id: 'decided', label: 'Decididas' },
            { id: 'all', label: 'Todas' },
          ].map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                filter === f.id ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 py-8 text-center">Carregando aprovações…</div>
      ) : approvals.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-4xl mb-3">✅</div>
          <p className="text-gray-500">Nenhuma aprovação {filter === 'pending' ? 'pendente' : 'encontrada'}.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {approvals.map(a => (
            <ApprovalCard
              key={a.approval_id}
              approval={a}
              expanded={expanded === a.approval_id}
              onToggle={() => setExpanded(expanded === a.approval_id ? null : a.approval_id)}
              onDecide={decide}
              deciding={deciding === a.approval_id}
              comment={expanded === a.approval_id ? comment : ''}
              onCommentChange={expanded === a.approval_id ? setComment : () => {}}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ApprovalCard({ approval: a, expanded, onToggle, onDecide, deciding, comment, onCommentChange }) {
  const isPending = a.status === 'pending' || a.status === 'escalated'
  const urgent = a.time_remaining_minutes != null && a.time_remaining_minutes < 30
  const data = a.data_to_approve || {}

  return (
    <div className={`bg-white border rounded-xl overflow-hidden transition ${
      urgent && isPending ? 'border-red-300 shadow-md' : 'border-gray-200'
    }`}>
      {/* Header */}
      <button onClick={onToggle} className="w-full px-5 py-4 flex items-start gap-4 text-left hover:bg-gray-50 transition">
        {/* Status icon */}
        <div className="text-2xl shrink-0 mt-0.5">
          {a.status === 'pending' ? '⏳' : a.status === 'escalated' ? '🔴' : a.status === 'approved' ? '✅' : a.status === 'rejected' ? '❌' : '⏰'}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900 text-sm">{_actionLabel(a.action)}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_STYLES[a.status] || STATUS_STYLES.pending}`}>
              {STATUS_LABELS[a.status] || a.status}
            </span>
            {urgent && isPending && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-300 animate-pulse">
                ⚠ {a.time_remaining_minutes}min restantes
              </span>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Agente: <span className="font-medium">{a.agent_type}</span>
            {' · '}Criado: {_formatDate(a.created_at)}
            {a.approved_by && <>{' · '}Decisão por: <span className="font-medium">{a.approved_by}</span></>}
          </div>
          {/* Preview of data */}
          {data.subject && <div className="text-sm text-gray-600 mt-1 truncate">"{data.subject}"</div>}
          {data.body && <div className="text-xs text-gray-400 mt-0.5 truncate">{data.body.slice(0, 120)}…</div>}
        </div>

        <span className="text-gray-300 text-sm shrink-0">{expanded ? '▲' : '▼'}</span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-100 px-5 py-4 space-y-4">
          {/* Data to approve */}
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Dados para aprovação</h4>
            <div className="bg-gray-50 rounded-lg p-3 text-sm">
              {Object.entries(data).length > 0 ? (
                <dl className="space-y-1">
                  {Object.entries(data).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="text-gray-500 font-medium min-w-[120px]">{k}:</dt>
                      <dd className="text-gray-700 whitespace-pre-wrap">{typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-gray-400 italic">Sem dados detalhados</p>
              )}
            </div>
          </div>

          {/* Context */}
          {a.context && Object.keys(a.context).length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Contexto</h4>
              <pre className="bg-gray-50 rounded-lg p-3 text-xs text-gray-600 overflow-x-auto">
                {JSON.stringify(a.context, null, 2)}
              </pre>
            </div>
          )}

          {/* Decision comment */}
          {a.decision_comment && (
            <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
              <p className="text-sm text-blue-700">💬 {a.decision_comment}</p>
            </div>
          )}

          {/* Action buttons (only for pending) */}
          {isPending && (
            <div className="space-y-3">
              <textarea
                value={comment}
                onChange={e => onCommentChange(e.target.value)}
                placeholder="Comentário opcional…"
                className="w-full border border-gray-200 rounded-lg p-2.5 text-sm resize-none focus:ring-2 focus:ring-violet-300 focus:border-transparent"
                rows={2}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => onDecide(a.approval_id, 'approved')}
                  disabled={deciding}
                  className="flex-1 py-2 px-4 bg-green-600 text-white rounded-lg font-medium text-sm hover:bg-green-700 disabled:opacity-50 transition"
                >
                  {deciding ? '…' : '✅ Aprovar'}
                </button>
                <button
                  onClick={() => onDecide(a.approval_id, 'rejected')}
                  disabled={deciding}
                  className="flex-1 py-2 px-4 bg-red-600 text-white rounded-lg font-medium text-sm hover:bg-red-700 disabled:opacity-50 transition"
                >
                  {deciding ? '…' : '❌ Rejeitar'}
                </button>
                <button
                  onClick={() => onDecide(a.approval_id, 'request_changes')}
                  disabled={deciding}
                  className="py-2 px-4 bg-blue-100 text-blue-700 rounded-lg font-medium text-sm hover:bg-blue-200 disabled:opacity-50 transition"
                >
                  ✏️ Pedir mudanças
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function _actionLabel(action) {
  const labels = {
    'commercial.followup.send': '📧 Envio de Follow-up',
    'commercial.proposal.send': '📄 Envio de Proposta',
    'proposal.send': '📄 Envio de Proposta',
    'apply.discount': '💰 Desconto',
    'process.refund': '💸 Reembolso',
    'cancel.contract': '🚫 Cancelamento',
    'executive.alert.broadcast': '📢 Alerta Executivo',
    'cs.retention.offer': '🛡️ Oferta de Retenção',
  }
  return labels[action] || action
}

function _formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
