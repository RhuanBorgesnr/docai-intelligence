import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../components/Toast'
import useDocumentStatus from '../hooks/useDocumentStatus'

const DOC_TYPES = [
  { value: 'other', label: 'Outro' },
  { value: 'contract', label: 'Contrato' },
  { value: 'invoice', label: 'Nota Fiscal' },
  { value: 'balance', label: 'Balanço' },
  { value: 'dre', label: 'DRE' },
  { value: 'certificate', label: 'Certidão' },
  { value: 'report', label: 'Relatório' },
]

const STEP_ICONS = {
  extracting_text: '📝',
  chunking: '✂️',
  embedding: '🧠',
  analyzing_financial: '📊',
  analyzing_clauses: '⚖️',
  extracting_metadata: '🏷️',
  completed: '✅',
  failed: '❌',
}

export default function Upload(){
  const [title, setTitle] = useState('')
  const [file, setFile] = useState(null)
  const [documentType, setDocumentType] = useState('other')
  const [referenceDate, setReferenceDate] = useState('')
  const [expirationDate, setExpirationDate] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [uploadedDocId, setUploadedDocId] = useState(null)
  const navigate = useNavigate()
  const toast = useToast()
  const { processingDocs, getDocStatus } = useDocumentStatus()

  // Track the uploaded document's live status
  const liveStatus = uploadedDocId ? getDocStatus(uploadedDocId) : null
  const isProcessing = liveStatus && liveStatus.status !== 'completed' && liveStatus.status !== 'failed'
  const isCompleted = liveStatus?.status === 'completed'
  const isFailed = liveStatus?.status === 'failed'

  async function handleSubmit(e){
    e.preventDefault()
    if(!file) return toast.warning('Selecione um arquivo')

    setLoading(true)
    setProgress(0)
    const formData = new FormData()
    formData.append('title', title || file.name.replace(/\.[^.]+$/, ''))
    formData.append('file', file)
    formData.append('document_type', documentType)
    if (referenceDate) formData.append('reference_date', referenceDate)
    if (expirationDate) formData.append('expiration_date', expirationDate)

    try{
      const res = await api.post('/documents/', formData, {
        headers: {'Content-Type': 'multipart/form-data'},
        onUploadProgress: (e) => {
          const pct = Math.round((e.loaded * 100) / e.total)
          setProgress(pct)
        }
      })
      setUploadedDocId(res.data.id)
      toast.success('Documento enviado! Acompanhe o processamento abaixo.')
    }catch(err){
      const msg = err.response?.data?.error || 'Falha no upload. Tente novamente.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  // After upload, show live processing tracker
  if (uploadedDocId) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="card">
          <div className="text-center mb-6">
            <div className="text-4xl mb-3">
              {isCompleted ? '✅' : isFailed ? '❌' : '🔬'}
            </div>
            <h3 className="text-xl font-semibold">
              {isCompleted ? 'Análise Concluída!' : isFailed ? 'Falha no Processamento' : 'Analisando Documento...'}
            </h3>
            <p className="text-sm text-gray-500 mt-1">
              {isCompleted
                ? 'Seu documento está pronto para consultas com IA'
                : isFailed
                  ? 'Ocorreu um erro durante o processamento'
                  : 'A IA está processando seu documento em tempo real'}
            </p>
          </div>

          {/* Live Processing Steps */}
          <div className="space-y-3 mb-6">
            {liveStatus ? (
              <div className={`rounded-xl border-2 px-5 py-4 transition-all duration-500 ${
                isFailed ? 'border-red-200 bg-red-50' 
                : isCompleted ? 'border-green-200 bg-green-50'
                : 'border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50'
              }`}>
                <div className="flex items-center gap-3">
                  {isProcessing && (
                    <svg className="animate-spin h-6 w-6 text-blue-500 flex-shrink-0" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                  )}
                  {isCompleted && <span className="text-2xl">✅</span>}
                  {isFailed && <span className="text-2xl">❌</span>}
                  
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-800">
                        {STEP_ICONS[liveStatus.status] || '⏳'} {liveStatus.message || liveStatus.label}
                      </span>
                      {isProcessing && liveStatus.step && (
                        <span className="text-xs font-medium text-blue-500 bg-blue-100 px-2 py-0.5 rounded-full">
                          Etapa {liveStatus.step}/{liveStatus.total_steps}
                        </span>
                      )}
                    </div>
                    {isProcessing && (
                      <div className="w-full bg-gray-200 rounded-full h-2 mt-3">
                        <div 
                          className="bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 h-2 rounded-full transition-all duration-1000 ease-out"
                          style={{ width: `${liveStatus.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              /* Waiting for first WS message */
              <div className="rounded-xl border-2 border-blue-200 bg-blue-50 px-5 py-4 flex items-center gap-3">
                <svg className="animate-spin h-6 w-6 text-blue-500" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                <div>
                  <span className="font-medium text-gray-800">Iniciando processamento...</span>
                  <p className="text-xs text-gray-500 mt-0.5">Conectando ao pipeline de IA</p>
                </div>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 justify-center">
            {isCompleted && (
              <>
                <button onClick={() => navigate(`/app/chat/${uploadedDocId}`)} className="btn">
                  💬 Conversar com o Documento
                </button>
                <button onClick={() => navigate('/app')} className="btn bg-gray-100 text-gray-700 hover:bg-gray-200">
                  Dashboard
                </button>
              </>
            )}
            {isFailed && (
              <>
                <button onClick={() => { setUploadedDocId(null); setFile(null); setProgress(0) }} className="btn">
                  Tentar Novamente
                </button>
                <button onClick={() => navigate('/app')} className="btn bg-gray-100 text-gray-700 hover:bg-gray-200">
                  Dashboard
                </button>
              </>
            )}
            {!isCompleted && !isFailed && (
              <button onClick={() => navigate('/app')} className="btn bg-gray-100 text-gray-700 hover:bg-gray-200 text-sm">
                Continuar no Dashboard (processamento segue em background)
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="card">
        <h3 className="text-xl font-semibold mb-2">Upload de Documento</h3>
        <p className="text-sm text-gray-500 mb-4">Envie o PDF do documento para processamento.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Título</label>
            <input
              className="input w-full"
              placeholder="Ex: Contrato de Prestação de Serviços"
              value={title}
              onChange={(e)=>setTitle(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Documento</label>
            <select
              className="input w-full"
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
            >
              {DOC_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Data de Referência</label>
              <input
                className="input w-full"
                type="date"
                value={referenceDate}
                onChange={(e)=>setReferenceDate(e.target.value)}
              />
              <p className="text-xs text-gray-400 mt-1">Competência do documento</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Data de Vencimento</label>
              <input
                className="input w-full"
                type="date"
                value={expirationDate}
                onChange={(e)=>setExpirationDate(e.target.value)}
              />
              <p className="text-xs text-gray-400 mt-1">Para alertas automáticos</p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Arquivo</label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-primary/50 transition cursor-pointer"
              onClick={() => document.getElementById('file-input').click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files[0]) }}
            >
              <input
                id="file-input"
                className="hidden"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.txt"
                onChange={(e)=>setFile(e.target.files[0])}
              />
              {file ? (
                <div>
                  <span className="text-2xl">📄</span>
                  <p className="text-sm font-medium text-gray-700 mt-2">{file.name}</p>
                  <p className="text-xs text-gray-400">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              ) : (
                <div>
                  <span className="text-3xl">⬆️</span>
                  <p className="text-sm text-gray-600 mt-2">Clique ou arraste o arquivo aqui</p>
                  <p className="text-xs text-gray-400 mt-1">PDF, imagem ou texto (máx. 20MB)</p>
                </div>
              )}
            </div>
          </div>

          {/* Progress bar */}
          {loading && (
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-primary h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button className="btn" disabled={loading}>
              {loading ? `Enviando... ${progress}%` : 'Enviar Documento'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
