import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../components/Toast'

const DOC_TYPES = [
  { value: 'other', label: 'Outro' },
  { value: 'contract', label: 'Contrato' },
  { value: 'invoice', label: 'Nota Fiscal' },
  { value: 'balance', label: 'Balanço' },
  { value: 'dre', label: 'DRE' },
  { value: 'certificate', label: 'Certidão' },
  { value: 'report', label: 'Relatório' },
]

export default function Upload(){
  const [title, setTitle] = useState('')
  const [file, setFile] = useState(null)
  const [documentType, setDocumentType] = useState('other')
  const [referenceDate, setReferenceDate] = useState('')
  const [expirationDate, setExpirationDate] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const navigate = useNavigate()
  const toast = useToast()

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
      await api.post('/documents/', formData, {
        headers: {'Content-Type': 'multipart/form-data'},
        onUploadProgress: (e) => {
          const pct = Math.round((e.loaded * 100) / e.total)
          setProgress(pct)
        }
      })
      toast.success('Documento enviado! A análise com IA está em andamento.')
      setTimeout(() => navigate('/app'), 1500)
    }catch(err){
      const msg = err.response?.data?.error || 'Falha no upload. Tente novamente.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
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
