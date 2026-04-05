import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'

const RISK_COLORS = {
  high: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', badge: 'bg-red-100 text-red-800' },
  medium: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700', badge: 'bg-yellow-100 text-yellow-800' },
  low: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', badge: 'bg-green-100 text-green-800' }
}

const CLAUSE_ICONS = {
  multa: '⚠️',
  reajuste: '📈',
  rescisao: '🚪',
  vigencia: '📅',
  renovacao: '🔄',
  confidencialidade: '🔒',
  garantia: '🛡️',
  pagamento: '💰',
  responsabilidade: '📋',
  foro: '⚖️',
  outro: '📄'
}

export default function Clauses() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [extracting, setExtracting] = useState(false)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    loadClauses()
  }, [id])

  async function loadClauses() {
    setLoading(true)
    try {
      const res = await api.get(`/documents/${id}/clauses/`)
      setData(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function handleExtract() {
    setExtracting(true)
    try {
      await api.post(`/documents/${id}/extract-clauses/`)
      setTimeout(() => {
        loadClauses()
        setExtracting(false)
      }, 5000)
    } catch (err) {
      alert('Erro ao iniciar extração')
      setExtracting(false)
    }
  }

  if (loading) {
    return <div className="text-center py-8">Carregando...</div>
  }

  if (!data) {
    return <div className="text-center py-8 text-red-500">Documento não encontrado</div>
  }

  const filteredClauses = filter === 'all'
    ? data.clauses
    : data.clauses.filter(c => c.risk_level === filter)

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/" className="text-sm text-primary hover:underline">&larr; Voltar</Link>
          <h1 className="text-2xl font-semibold mt-1">Cláusulas do Contrato</h1>
          <p className="text-sm text-gray-500">{data.document_title || `Documento ${id}`}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleExtract}
            disabled={extracting}
            className="btn bg-gray-100 text-gray-700 hover:bg-gray-200"
          >
            {extracting ? 'Extraindo...' : 'Re-extrair'}
          </button>
          <Link to={`/chat/${id}`} className="btn">Chat</Link>
        </div>
      </div>

      {/* Summary Cards */}
      {data.clauses.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="card text-center border-l-4 border-red-400">
            <div className="text-3xl font-bold text-red-600">{data.by_risk?.high?.length || 0}</div>
            <div className="text-sm text-gray-500">Alto Risco</div>
          </div>
          <div className="card text-center border-l-4 border-yellow-400">
            <div className="text-3xl font-bold text-yellow-600">{data.by_risk?.medium?.length || 0}</div>
            <div className="text-sm text-gray-500">Médio Risco</div>
          </div>
          <div className="card text-center border-l-4 border-green-400">
            <div className="text-3xl font-bold text-green-600">{data.by_risk?.low?.length || 0}</div>
            <div className="text-sm text-gray-500">Baixo Risco</div>
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2 mb-4">
        {['all', 'high', 'medium', 'low'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded text-sm transition ${
              filter === f ? 'bg-primary text-white' : 'bg-gray-100 hover:bg-gray-200'
            }`}
          >
            {f === 'all' ? 'Todas' : f === 'high' ? 'Alto Risco' : f === 'medium' ? 'Médio' : 'Baixo'}
          </button>
        ))}
      </div>

      {data.clauses.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-500 mb-4">Nenhuma cláusula extraída ainda.</p>
          <button onClick={handleExtract} disabled={extracting} className="btn">
            {extracting ? 'Extraindo...' : 'Extrair Cláusulas'}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredClauses.map(clause => {
            const colors = RISK_COLORS[clause.risk_level] || RISK_COLORS.medium
            const icon = CLAUSE_ICONS[clause.clause_type] || '📄'

            return (
              <div key={clause.id} className={`card ${colors.bg} ${colors.border} border`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{icon}</span>
                    <div>
                      <h3 className="font-semibold text-gray-900">{clause.title}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded ${colors.badge}`}>
                        {clause.clause_type_display}
                      </span>
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded font-medium ${colors.badge}`}>
                    {clause.risk_level_display}
                  </span>
                </div>

                <p className="mt-3 text-gray-700 text-sm">{clause.content}</p>

                {clause.extracted_value && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs text-gray-500">Valor identificado:</span>
                    <span className="text-sm font-medium text-gray-800 bg-white px-2 py-0.5 rounded">
                      {clause.extracted_value}
                    </span>
                  </div>
                )}

                {clause.summary && (
                  <p className="mt-2 text-xs text-gray-500 italic">{clause.summary}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
