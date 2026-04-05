import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell
} from 'recharts'
import api from '../services/api'

function formatCurrency(value) {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    notation: 'compact',
    maximumFractionDigits: 1
  }).format(value)
}

function formatPercent(value) {
  if (value === null || value === undefined) return '-'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function getVariationColor(value) {
  if (value === null || value === undefined) return 'text-gray-400'
  if (value > 0) return 'text-green-600'
  if (value < 0) return 'text-red-600'
  return 'text-gray-600'
}

function getVariationBg(value) {
  if (value === null || value === undefined) return 'bg-gray-50'
  if (value > 0) return 'bg-green-50'
  if (value < 0) return 'bg-red-50'
  return 'bg-gray-50'
}

export default function Compare() {
  const [documents, setDocuments] = useState([])
  const [doc1, setDoc1] = useState('')
  const [doc2, setDoc2] = useState('')
  const [comparison, setComparison] = useState(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    loadDocuments()
  }, [])

  async function loadDocuments() {
    try {
      const res = await api.get('/documents/financial/comparable/')
      setDocuments(res.data)
      if (res.data.length >= 2) {
        setDoc1(res.data[0].id.toString())
        setDoc2(res.data[1].id.toString())
      }
    } catch (err) {
      console.error(err)
    }
  }

  async function loadComparison() {
    if (!doc1 || !doc2 || doc1 === doc2) return

    setLoading(true)
    try {
      const res = await api.get(`/documents/financial/compare/?doc1=${doc1}&doc2=${doc2}`)
      setComparison(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (doc1 && doc2 && doc1 !== doc2) {
      loadComparison()
    }
  }, [doc1, doc2])

  async function handleDownloadPDF() {
    if (!doc1 || !doc2) return
    setDownloading(true)
    try {
      const response = await api.get(`/documents/financial/report/?doc1=${doc1}&doc2=${doc2}`, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `comparativo_${doc1}_vs_${doc2}.pdf`)
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

  // Build chart data
  function buildChartData() {
    if (!comparison) return []

    return comparison.comparison
      .filter(c => c.value_period_1 !== null && c.value_period_2 !== null)
      .filter(c => !c.indicator_type.includes('margem'))
      .slice(0, 8)
      .map(c => ({
        name: c.indicator_label.replace(' Líquida', '').replace(' Bruta', ' Br.'),
        periodo1: c.value_period_1,
        periodo2: c.value_period_2
      }))
  }

  const hasDocuments = documents.length >= 2

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/" className="text-sm text-primary hover:underline">&larr; Voltar</Link>
          <h1 className="text-2xl font-semibold mt-1">Comparativo de Períodos</h1>
          <p className="text-sm text-gray-500">Compare indicadores financeiros entre dois documentos</p>
        </div>
        {comparison && (
          <button
            onClick={handleDownloadPDF}
            disabled={downloading}
            className="btn bg-green-600 text-white hover:bg-green-700"
          >
            {downloading ? 'Gerando...' : 'Baixar PDF'}
          </button>
        )}
      </div>

      {!hasDocuments ? (
        <div className="card text-center py-12">
          <p className="text-gray-500 mb-4">Você precisa de pelo menos 2 documentos financeiros com indicadores extraídos.</p>
          <Link to="/upload" className="btn">Fazer Upload</Link>
        </div>
      ) : (
        <>
          {/* Document Selectors */}
          <div className="card mb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Período 1 (Base)</label>
                <select
                  value={doc1}
                  onChange={(e) => setDoc1(e.target.value)}
                  className="input w-full"
                >
                  <option value="">Selecione...</option>
                  {documents.map(d => (
                    <option key={d.id} value={d.id} disabled={d.id.toString() === doc2}>
                      {d.title} {d.reference_date ? `(${d.reference_date})` : ''} - {d.document_type_display}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Período 2 (Comparação)</label>
                <select
                  value={doc2}
                  onChange={(e) => setDoc2(e.target.value)}
                  className="input w-full"
                >
                  <option value="">Selecione...</option>
                  {documents.map(d => (
                    <option key={d.id} value={d.id} disabled={d.id.toString() === doc1}>
                      {d.title} {d.reference_date ? `(${d.reference_date})` : ''} - {d.document_type_display}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {loading && (
            <div className="text-center py-8">Carregando comparação...</div>
          )}

          {comparison && !loading && (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                {comparison.comparison
                  .filter(c => ['receita_liquida', 'lucro_liquido', 'ebitda', 'margem_liquida'].includes(c.indicator_type))
                  .map(c => (
                    <div key={c.indicator_type} className={`card ${getVariationBg(c.variation_pct)}`}>
                      <div className="text-sm text-gray-500">{c.indicator_label}</div>
                      <div className="text-xl font-bold mt-1">
                        {c.indicator_type.includes('margem')
                          ? `${c.value_period_2?.toFixed(1)}%`
                          : formatCurrency(c.value_period_2)
                        }
                      </div>
                      <div className={`text-sm font-medium mt-1 ${getVariationColor(c.variation_pct)}`}>
                        {formatPercent(c.variation_pct)} vs período anterior
                      </div>
                    </div>
                  ))
                }
              </div>

              {/* Comparison Chart */}
              <div className="card mb-6">
                <h3 className="text-lg font-semibold mb-4">Comparativo Visual</h3>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={buildChartData()} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis type="number" tickFormatter={formatCurrency} tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={100} />
                      <Tooltip formatter={(value) => formatCurrency(value)} />
                      <Legend />
                      <Bar
                        dataKey="periodo1"
                        name={comparison.period_1.reference_date || 'Período 1'}
                        fill="#94a3b8"
                      />
                      <Bar
                        dataKey="periodo2"
                        name={comparison.period_2.reference_date || 'Período 2'}
                        fill="#2563eb"
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Detailed Table */}
              <div className="card">
                <h3 className="text-lg font-semibold mb-4">Comparativo Detalhado</h3>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-sm text-gray-500 border-b">
                        <th className="py-3">Indicador</th>
                        <th className="py-3 text-right">
                          {comparison.period_1.reference_date || comparison.period_1.document_title}
                        </th>
                        <th className="py-3 text-right">
                          {comparison.period_2.reference_date || comparison.period_2.document_title}
                        </th>
                        <th className="py-3 text-right">Variação</th>
                        <th className="py-3 text-right">%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.comparison.map((c, idx) => (
                        <tr key={c.indicator_type} className={idx % 2 === 0 ? 'bg-gray-50' : ''}>
                          <td className="py-3 font-medium">{c.indicator_label}</td>
                          <td className="py-3 text-right">
                            {c.indicator_type.includes('margem')
                              ? (c.value_period_1 !== null ? `${c.value_period_1.toFixed(2)}%` : '-')
                              : formatCurrency(c.value_period_1)
                            }
                          </td>
                          <td className="py-3 text-right">
                            {c.indicator_type.includes('margem')
                              ? (c.value_period_2 !== null ? `${c.value_period_2.toFixed(2)}%` : '-')
                              : formatCurrency(c.value_period_2)
                            }
                          </td>
                          <td className={`py-3 text-right ${getVariationColor(c.variation)}`}>
                            {c.indicator_type.includes('margem')
                              ? (c.variation !== null ? `${c.variation > 0 ? '+' : ''}${c.variation.toFixed(2)}pp` : '-')
                              : (c.variation !== null ? formatCurrency(c.variation) : '-')
                            }
                          </td>
                          <td className={`py-3 text-right font-medium ${getVariationColor(c.variation_pct)}`}>
                            {formatPercent(c.variation_pct)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Legend */}
                <div className="mt-4 pt-4 border-t text-sm text-gray-500">
                  <div className="flex gap-4">
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-3 rounded bg-green-100"></span>
                      Crescimento
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-3 rounded bg-red-100"></span>
                      Redução
                    </span>
                    <span className="text-gray-400 ml-auto">pp = pontos percentuais</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
