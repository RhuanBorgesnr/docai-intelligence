import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'
import api from '../services/api'

const COLORS = {
  receita_liquida: '#2563eb',
  lucro_bruto: '#16a34a',
  ebitda: '#9333ea',
  lucro_liquido: '#059669'
}

const INDICATOR_OPTIONS = [
  { value: 'receita_liquida', label: 'Receita Líquida' },
  { value: 'lucro_bruto', label: 'Lucro Bruto' },
  { value: 'ebitda', label: 'EBITDA' },
  { value: 'lucro_liquido', label: 'Lucro Líquido' },
  { value: 'receita_bruta', label: 'Receita Bruta' },
  { value: 'custo', label: 'Custos' },
  { value: 'despesas_op', label: 'Despesas Operacionais' },
]

function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    notation: 'compact',
    maximumFractionDigits: 1
  }).format(value)
}

function CustomTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-3 shadow-lg rounded border">
        <p className="text-sm font-medium text-gray-600">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} style={{ color: entry.color }} className="text-sm font-bold">
            {entry.name}: {formatCurrency(entry.value)}
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function Charts() {
  const [allData, setAllData] = useState(null)
  const [singleData, setSingleData] = useState(null)
  const [selectedIndicator, setSelectedIndicator] = useState('receita_liquida')
  const [loading, setLoading] = useState(true)
  const [chartType, setChartType] = useState('line')

  useEffect(() => {
    loadAllData()
  }, [])

  useEffect(() => {
    loadSingleIndicator(selectedIndicator)
  }, [selectedIndicator])

  async function loadAllData() {
    try {
      const res = await api.get('/documents/financial/history/all/')
      setAllData(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function loadSingleIndicator(type) {
    try {
      const res = await api.get(`/documents/financial/history/?type=${type}`)
      setSingleData(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  // Build combined chart data
  function buildCombinedData() {
    if (!allData) return []

    const periodsMap = {}

    Object.entries(allData).forEach(([key, value]) => {
      value.data.forEach(item => {
        if (!periodsMap[item.period]) {
          periodsMap[item.period] = { period: item.period, period_label: item.period_label }
        }
        periodsMap[item.period][key] = item.value
      })
    })

    return Object.values(periodsMap).sort((a, b) => a.period.localeCompare(b.period))
  }

  if (loading) {
    return <div className="text-center py-8">Carregando...</div>
  }

  const combinedData = buildCombinedData()
  const hasData = combinedData.length > 0

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/" className="text-sm text-primary hover:underline">&larr; Voltar</Link>
          <h1 className="text-2xl font-semibold mt-1">Evolução Financeira</h1>
          <p className="text-sm text-gray-500">Acompanhe a evolução dos indicadores ao longo do tempo</p>
        </div>
      </div>

      {!hasData ? (
        <div className="card text-center py-12">
          <p className="text-gray-500 mb-4">Nenhum dado financeiro disponível.</p>
          <p className="text-sm text-gray-400">
            Faça upload de documentos DRE ou Balanço com data de referência para visualizar os gráficos.
          </p>
          <Link to="/upload" className="btn mt-4">Fazer Upload</Link>
        </div>
      ) : (
        <>
          {/* Combined Chart */}
          <div className="card mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Visão Geral</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => setChartType('line')}
                  className={`px-3 py-1 rounded text-sm ${chartType === 'line' ? 'bg-primary text-white' : 'bg-gray-100'}`}
                >
                  Linha
                </button>
                <button
                  onClick={() => setChartType('bar')}
                  className={`px-3 py-1 rounded text-sm ${chartType === 'bar' ? 'bg-primary text-white' : 'bg-gray-100'}`}
                >
                  Barras
                </button>
              </div>
            </div>

            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                {chartType === 'line' ? (
                  <LineChart data={combinedData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="period_label" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={formatCurrency} tick={{ fontSize: 12 }} width={80} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend />
                    {allData.receita_liquida && (
                      <Line
                        type="monotone"
                        dataKey="receita_liquida"
                        name={allData.receita_liquida.label}
                        stroke={COLORS.receita_liquida}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                    )}
                    {allData.lucro_bruto && (
                      <Line
                        type="monotone"
                        dataKey="lucro_bruto"
                        name={allData.lucro_bruto.label}
                        stroke={COLORS.lucro_bruto}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                    )}
                    {allData.ebitda && (
                      <Line
                        type="monotone"
                        dataKey="ebitda"
                        name={allData.ebitda.label}
                        stroke={COLORS.ebitda}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                    )}
                    {allData.lucro_liquido && (
                      <Line
                        type="monotone"
                        dataKey="lucro_liquido"
                        name={allData.lucro_liquido.label}
                        stroke={COLORS.lucro_liquido}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                    )}
                  </LineChart>
                ) : (
                  <BarChart data={combinedData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="period_label" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={formatCurrency} tick={{ fontSize: 12 }} width={80} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend />
                    {allData.receita_liquida && (
                      <Bar dataKey="receita_liquida" name={allData.receita_liquida.label} fill={COLORS.receita_liquida} />
                    )}
                    {allData.lucro_bruto && (
                      <Bar dataKey="lucro_bruto" name={allData.lucro_bruto.label} fill={COLORS.lucro_bruto} />
                    )}
                    {allData.ebitda && (
                      <Bar dataKey="ebitda" name={allData.ebitda.label} fill={COLORS.ebitda} />
                    )}
                    {allData.lucro_liquido && (
                      <Bar dataKey="lucro_liquido" name={allData.lucro_liquido.label} fill={COLORS.lucro_liquido} />
                    )}
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>

          {/* Single Indicator Chart */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Indicador Individual</h3>
              <select
                value={selectedIndicator}
                onChange={(e) => setSelectedIndicator(e.target.value)}
                className="input w-48"
              >
                {INDICATOR_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            {singleData && singleData.data.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={singleData.data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="period_label" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={formatCurrency} tick={{ fontSize: 12 }} width={80} />
                    <Tooltip content={<CustomTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="value"
                      name={singleData.indicator_label}
                      stroke={COLORS[selectedIndicator] || '#6b7280'}
                      strokeWidth={3}
                      dot={{ r: 5 }}
                      activeDot={{ r: 8 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                Sem dados para este indicador
              </div>
            )}

            {/* Data table */}
            {singleData && singleData.data.length > 0 && (
              <div className="mt-4 border-t pt-4">
                <h4 className="text-sm font-medium text-gray-600 mb-2">Dados</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-500">
                        <th className="py-2">Período</th>
                        <th className="py-2">Valor</th>
                        <th className="py-2">Documento</th>
                      </tr>
                    </thead>
                    <tbody>
                      {singleData.data.map((item, idx) => (
                        <tr key={idx} className="border-t">
                          <td className="py-2">{item.period_label}</td>
                          <td className="py-2 font-medium">{formatCurrency(item.value)}</td>
                          <td className="py-2">
                            <Link to={`/indicators/${item.document_id}`} className="text-primary hover:underline">
                              {item.document_title}
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
