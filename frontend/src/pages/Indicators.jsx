import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'

const INDICATOR_ORDER = [
  'receita_bruta',
  'receita_liquida',
  'custo',
  'lucro_bruto',
  'despesas_op',
  'ebitda',
  'lucro_op',
  'lucro_liquido',
  'ativo_total',
  'passivo_total',
  'patrimonio_liq',
  'margem_bruta',
  'margem_liquida',
  'margem_ebitda',
]

function formatValue(value, indicatorType) {
  const isPercent = indicatorType.includes('margem')
  if (isPercent) {
    return `${Number(value).toFixed(2)}%`
  }
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(value)
}

function getIndicatorColor(indicatorType) {
  if (indicatorType.includes('lucro') || indicatorType === 'ebitda') return 'text-green-600'
  if (indicatorType.includes('custo') || indicatorType.includes('despesas')) return 'text-red-600'
  if (indicatorType.includes('margem')) return 'text-blue-600'
  return 'text-gray-900'
}

export default function Indicators() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [extracting, setExtracting] = useState(false)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    loadIndicators()
  }, [id])

  async function loadIndicators() {
    setLoading(true)
    try {
      const res = await api.get(`/documents/${id}/indicators/`)
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
      await api.post(`/documents/${id}/extract-indicators/`)
      setTimeout(() => {
        loadIndicators()
        setExtracting(false)
      }, 3000)
    } catch (err) {
      alert('Erro ao iniciar extração')
      setExtracting(false)
    }
  }

  async function handleDownloadPDF() {
    setDownloading(true)
    try {
      const response = await api.get(`/documents/${id}/report/`, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `relatorio_${id}.pdf`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert('Erro ao gerar PDF')
    } finally {
      setDownloading(false)
    }
  }

  if (loading) {
    return <div className="text-center py-8">Carregando...</div>
  }

  if (!data) {
    return <div className="text-center py-8 text-red-500">Documento não encontrado</div>
  }

  // Sort indicators by predefined order
  const sortedIndicators = [...(data.indicators || [])].sort((a, b) => {
    const aIndex = INDICATOR_ORDER.indexOf(a.indicator_type)
    const bIndex = INDICATOR_ORDER.indexOf(b.indicator_type)
    return aIndex - bIndex
  })

  const incomeIndicators = sortedIndicators.filter(i =>
    ['receita_bruta', 'receita_liquida', 'custo', 'lucro_bruto', 'despesas_op', 'ebitda', 'lucro_op', 'lucro_liquido'].includes(i.indicator_type)
  )

  const balanceIndicators = sortedIndicators.filter(i =>
    ['ativo_total', 'passivo_total', 'patrimonio_liq'].includes(i.indicator_type)
  )

  const marginIndicators = sortedIndicators.filter(i =>
    i.indicator_type.includes('margem')
  )

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/" className="text-sm text-primary hover:underline">&larr; Voltar</Link>
          <h1 className="text-2xl font-semibold mt-1">Indicadores Financeiros</h1>
          <p className="text-sm text-gray-500">{data.document_title || `Documento ${id}`}</p>
          {data.reference_date && (
            <p className="text-sm text-gray-400">Período: {data.reference_date}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleDownloadPDF}
            disabled={downloading || sortedIndicators.length === 0}
            className="btn bg-green-600 text-white hover:bg-green-700"
          >
            {downloading ? 'Gerando...' : 'Baixar PDF'}
          </button>
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

      {sortedIndicators.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-500 mb-4">Nenhum indicador financeiro extraído ainda.</p>
          <button onClick={handleExtract} disabled={extracting} className="btn">
            {extracting ? 'Extraindo...' : 'Extrair Indicadores'}
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Margin Cards */}
          {marginIndicators.length > 0 && (
            <div className="grid grid-cols-3 gap-4">
              {marginIndicators.map(ind => (
                <div key={ind.id} className="card text-center">
                  <div className={`text-3xl font-bold ${getIndicatorColor(ind.indicator_type)}`}>
                    {formatValue(ind.value, ind.indicator_type)}
                  </div>
                  <div className="text-sm text-gray-500 mt-1">{ind.indicator_type_display}</div>
                </div>
              ))}
            </div>
          )}

          {/* Income Statement */}
          {incomeIndicators.length > 0 && (
            <div className="card">
              <h3 className="text-lg font-semibold mb-4">Demonstração de Resultado</h3>
              <div className="space-y-3">
                {incomeIndicators.map(ind => (
                  <div key={ind.id} className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0">
                    <span className="text-gray-700">{ind.indicator_type_display}</span>
                    <span className={`font-medium ${getIndicatorColor(ind.indicator_type)}`}>
                      {formatValue(ind.value, ind.indicator_type)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Balance Sheet */}
          {balanceIndicators.length > 0 && (
            <div className="card">
              <h3 className="text-lg font-semibold mb-4">Balanço Patrimonial</h3>
              <div className="space-y-3">
                {balanceIndicators.map(ind => (
                  <div key={ind.id} className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0">
                    <span className="text-gray-700">{ind.indicator_type_display}</span>
                    <span className={`font-medium ${getIndicatorColor(ind.indicator_type)}`}>
                      {formatValue(ind.value, ind.indicator_type)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
