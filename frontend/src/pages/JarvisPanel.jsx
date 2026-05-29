/**
 * JarvisPanel — executive briefing + natural language ask UI.
 *
 * Displays alerts, KPIs, and a chat-like input to ask Jarvis questions.
 */
import React, { useState } from 'react'
import useJarvis from '../hooks/useJarvis'

const QUICK_QUESTIONS = [
  'Qual o resumo geral?',
  'Tem algum alerta?',
  'Quantos cases ativos?',
  'Aprovações pendentes?',
  'Status das notificações?',
]

export default function JarvisPanel() {
  const { briefing, loadingBriefing, error, refetchBriefing, ask } = useJarvis()
  const [question, setQuestion] = useState('')
  const [conversation, setConversation] = useState([])
  const [asking, setAsking] = useState(false)

  const handleAsk = async (q) => {
    const text = (q || question).trim()
    if (!text) return
    setAsking(true)
    setConversation((prev) => [...prev, { role: 'user', text }])
    setQuestion('')
    try {
      const res = await ask(text)
      setConversation((prev) => [
        ...prev,
        {
          role: 'jarvis',
          text: res.answer,
          references: res.references,
          context_used: res.context_used,
        },
      ])
    } catch {
      setConversation((prev) => [
        ...prev,
        { role: 'jarvis', text: 'Desculpe, ocorreu um erro ao processar sua pergunta.', error: true },
      ])
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg">
            <span className="text-white text-lg">🧠</span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Jarvis</h1>
            <p className="text-sm text-gray-500">Agente executivo — briefing &amp; insights</p>
          </div>
        </div>
        <button
          onClick={refetchBriefing}
          className="text-sm px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-600 transition"
          title="Atualizar briefing"
        >
          🔄 Atualizar
        </button>
      </div>

      {/* Briefing Cards */}
      {loadingBriefing && !briefing && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-violet-600" />
        </div>
      )}

      {error && !briefing && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
          <p className="text-red-600 font-medium">Erro ao carregar briefing</p>
          <p className="text-sm text-red-400 mt-1">Verifique se o backend está rodando</p>
        </div>
      )}

      {briefing && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KpiCard
              icon="📂" label="Cases Ativos"
              value={briefing.summary?.active_cases ?? 0}
              color="text-blue-600"
            />
            <KpiCard
              icon="✅" label="Concluídos (30d)"
              value={briefing.summary?.completed_30d ?? 0}
              color="text-green-600"
            />
            <KpiCard
              icon="🔐" label="Aprovações Pendentes"
              value={briefing.summary?.pending_approvals ?? 0}
              color="text-amber-600"
              warn={briefing.summary?.overdue_approvals > 0}
            />
            <KpiCard
              icon="📨" label="Notificações"
              value={briefing.summary?.pending_notifications ?? 0}
              color="text-indigo-600"
            />
          </div>

          {/* Alerts */}
          {briefing.alerts?.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-lg">⚠️</span>
                <h2 className="font-semibold text-amber-800">
                  {briefing.alert_count} Alerta{briefing.alert_count > 1 ? 's' : ''}
                </h2>
              </div>
              <ul className="space-y-1.5">
                {briefing.alerts.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-amber-700">
                    <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {briefing.alerts?.length === 0 && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3">
              <span className="text-lg">✅</span>
              <p className="text-sm text-green-700 font-medium">Nenhum alerta ativo — tudo operando normalmente.</p>
            </div>
          )}

          {/* Pipeline Breakdown */}
          {briefing.pipeline_breakdown && Object.keys(briefing.pipeline_breakdown).length > 0 && (
            <div className="bg-white border border-gray-100 rounded-xl shadow-sm p-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">Pipeline por Estado</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(briefing.pipeline_breakdown).map(([state, count]) => (
                  <span
                    key={state}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-100 text-xs font-medium text-gray-700"
                  >
                    {state} <span className="font-bold text-gray-900">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Conversation */}
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
          <span className="text-sm">💬</span>
          <h2 className="text-sm font-semibold text-gray-700">Pergunte ao Jarvis</h2>
        </div>

        {/* Quick questions */}
        <div className="px-4 py-3 flex flex-wrap gap-2 border-b border-gray-50">
          {QUICK_QUESTIONS.map((qq) => (
            <button
              key={qq}
              onClick={() => handleAsk(qq)}
              disabled={asking}
              className="text-xs px-3 py-1.5 rounded-full bg-violet-50 text-violet-700 hover:bg-violet-100 transition disabled:opacity-50"
            >
              {qq}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div className="max-h-80 overflow-y-auto px-4 py-3 space-y-3">
          {conversation.length === 0 && (
            <p className="text-center text-gray-400 text-sm py-6">
              Faça uma pergunta ou use os atalhos acima
            </p>
          )}
          {conversation.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-violet-600 text-white'
                    : msg.error
                      ? 'bg-red-50 text-red-700 border border-red-200'
                      : 'bg-gray-100 text-gray-800'
                }`}
              >
                {msg.text}
                {msg.context_used?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-200 flex flex-wrap gap-1">
                    {msg.context_used.map((c) => (
                      <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-500">
                        {c}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {asking && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-xl px-4 py-3 flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-violet-500" />
                <span className="text-sm text-gray-500">Analisando...</span>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <form
          onSubmit={(e) => { e.preventDefault(); handleAsk() }}
          className="px-4 py-3 border-t border-gray-100 flex gap-2"
        >
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Pergunte sobre cases, alertas, aprovações..."
            disabled={asking}
            className="flex-1 px-4 py-2 rounded-lg bg-gray-50 border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={asking || !question.trim()}
            className="px-4 py-2 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Enviar
          </button>
        </form>
      </div>
    </div>
  )
}

function KpiCard({ icon, label, value, color, warn }) {
  return (
    <div className={`bg-white rounded-xl border shadow-sm p-4 ${warn ? 'border-amber-300 bg-amber-50' : 'border-gray-100'}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{icon}</span>
        <span className={`text-2xl font-bold ${color}`}>{value}</span>
      </div>
      <p className="text-[11px] text-gray-500">{label}</p>
      {warn && <p className="text-[10px] text-amber-600 mt-1 font-medium">⚠ Há vencidas</p>}
    </div>
  )
}
