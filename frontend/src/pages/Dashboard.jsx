import React, { useEffect, useState } from 'react'
import api from '../services/api'
import { Link } from 'react-router-dom'

const DOC_TYPES = [
  { value: '', label: 'Todos' },
  { value: 'contract', label: 'Contrato' },
  { value: 'invoice', label: 'Nota Fiscal' },
  { value: 'balance', label: 'Balanço' },
  { value: 'dre', label: 'DRE' },
  { value: 'certificate', label: 'Certidão' },
  { value: 'report', label: 'Relatório' },
  { value: 'other', label: 'Outro' },
]

const FINANCIAL_TYPES = ['dre', 'balance']

function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    notation: 'compact'
  }).format(value)
}

export default function Dashboard(){
  const [docs, setDocs] = useState([])
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('')
  const [expiringDocs, setExpiringDocs] = useState([])
  const [financial, setFinancial] = useState(null)

  useEffect(()=>{
    loadData()
  },[filter])

  async function loadData(){
    try {
      const params = filter ? `?document_type=${filter}` : ''
      const [docsRes, statsRes, expiringRes, financialRes] = await Promise.all([
        api.get(`/documents/${params}`),
        api.get('/documents/stats/'),
        api.get('/documents/expiring/?days=7'),
        api.get('/documents/financial/')
      ])
      setDocs(docsRes.data)
      setStats(statsRes.data)
      setExpiringDocs(expiringRes.data)
      setFinancial(financialRes.data)
    } catch {
      setDocs([])
    }
  }

  function getExpirationBadge(doc) {
    if (!doc.days_until_expiration && doc.days_until_expiration !== 0) return null
    const days = doc.days_until_expiration
    if (days < 0) {
      return <span className="px-2 py-1 text-xs rounded bg-red-100 text-red-700">Vencido</span>
    }
    if (days <= 7) {
      return <span className="px-2 py-1 text-xs rounded bg-orange-100 text-orange-700">Vence em {days}d</span>
    }
    if (days <= 30) {
      return <span className="px-2 py-1 text-xs rounded bg-yellow-100 text-yellow-700">Vence em {days}d</span>
    }
    return <span className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-600">Vence em {days}d</span>
  }

  const hasFinancialData = financial && financial.docs_with_financial_data > 0

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Meus Documentos</h1>
          <p className="text-sm text-gray-500">Gerencie e pergunte sobre seus documentos</p>
        </div>
        <Link to="/upload" className="btn">+ Upload</Link>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <div className="text-3xl font-bold text-primary">{stats.total}</div>
            <div className="text-sm text-gray-500">Total de Docs</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-orange-500">{stats.expiring_7_days}</div>
            <div className="text-sm text-gray-500">Vencem em 7 dias</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-yellow-500">{stats.expiring_30_days}</div>
            <div className="text-sm text-gray-500">Vencem em 30 dias</div>
          </div>
          <div className="card text-center">
            <div className="text-3xl font-bold text-red-500">{stats.expired}</div>
            <div className="text-sm text-gray-500">Vencidos</div>
          </div>
        </div>
      )}

      {/* Financial Indicators Summary */}
      {hasFinancialData && financial.latest_indicators && (
        <div className="card bg-blue-50 border-l-4 border-blue-400 mb-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-blue-700 font-semibold">📊 Indicadores Financeiros</span>
            <span className="text-xs text-blue-500">{financial.docs_with_financial_data} doc(s) com dados</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {financial.latest_indicators.receita_liquida && (
              <div>
                <div className="text-lg font-bold text-gray-800">
                  {formatCurrency(financial.latest_indicators.receita_liquida.value)}
                </div>
                <div className="text-xs text-gray-500">Receita Líquida</div>
              </div>
            )}
            {financial.latest_indicators.lucro_liquido && (
              <div>
                <div className="text-lg font-bold text-green-600">
                  {formatCurrency(financial.latest_indicators.lucro_liquido.value)}
                </div>
                <div className="text-xs text-gray-500">Lucro Líquido</div>
              </div>
            )}
            {financial.latest_indicators.ebitda && (
              <div>
                <div className="text-lg font-bold text-blue-600">
                  {formatCurrency(financial.latest_indicators.ebitda.value)}
                </div>
                <div className="text-xs text-gray-500">EBITDA</div>
              </div>
            )}
            {financial.latest_indicators.margem_liquida && (
              <div>
                <div className="text-lg font-bold text-purple-600">
                  {Number(financial.latest_indicators.margem_liquida.value).toFixed(1)}%
                </div>
                <div className="text-xs text-gray-500">Margem Líquida</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Expiring Alert */}
      {expiringDocs.length > 0 && (
        <div className="card bg-orange-50 border-l-4 border-orange-400 mb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-orange-600 font-semibold">⚠️ Atenção: Documentos com vencimento próximo</span>
          </div>
          <div className="space-y-2">
            {expiringDocs.slice(0, 3).map(d => (
              <div key={d.id} className="flex items-center justify-between text-sm">
                <span>{d.title || (d.file && d.file.split('/').pop())}</span>
                <div className="flex items-center gap-2">
                  {getExpirationBadge(d)}
                  <Link to={`/chat/${d.id}`} className="text-primary hover:underline">Ver</Link>
                </div>
              </div>
            ))}
            {expiringDocs.length > 3 && (
              <div className="text-sm text-gray-500">...e mais {expiringDocs.length - 3} documento(s)</div>
            )}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {DOC_TYPES.map(t => (
          <button
            key={t.value}
            onClick={() => setFilter(t.value)}
            className={`px-3 py-1 rounded text-sm transition ${
              filter === t.value
                ? 'bg-primary text-white'
                : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Document List */}
      <div className="grid grid-cols-1 gap-4">
        {docs.length===0 && (
          <div className="card text-gray-500">Nenhum documento encontrado. Faça upload para começar.</div>
        )}

        {docs.map(d=> (
          <div key={d.id} className="card flex flex-col md:flex-row md:items-center md:justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <div className="text-lg font-medium">{d.title || (d.file && d.file.split('/').pop())}</div>
                {getExpirationBadge(d)}
              </div>
              <div className="flex items-center gap-3 text-sm text-gray-500 mt-1">
                <span className="px-2 py-0.5 bg-gray-100 rounded">{d.document_type_display || 'Outro'}</span>
                <span>{d.processing_status || 'unknown'}</span>
                {d.expiration_date && <span>Venc: {d.expiration_date}</span>}
              </div>
            </div>

            <div className="mt-3 md:mt-0 flex items-center gap-2">
              {FINANCIAL_TYPES.includes(d.document_type) && d.processing_status === 'completed' && (
                <Link to={`/indicators/${d.id}`} className="btn bg-blue-100 text-blue-700 hover:bg-blue-200">
                  Indicadores
                </Link>
              )}
              {d.document_type === 'contract' && d.processing_status === 'completed' && (
                <Link to={`/clauses/${d.id}`} className="btn bg-purple-100 text-purple-700 hover:bg-purple-200">
                  Cláusulas
                </Link>
              )}
              <Link to={`/chat/${d.id}`} className="btn">Abrir</Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
