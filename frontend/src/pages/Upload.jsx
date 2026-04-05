import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'

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
  const navigate = useNavigate()

  async function handleSubmit(e){
    e.preventDefault()
    if(!file) return alert('Selecione um arquivo')

    setLoading(true)
    const formData = new FormData()
    formData.append('title', title)
    formData.append('file', file)
    formData.append('document_type', documentType)
    if (referenceDate) formData.append('reference_date', referenceDate)
    if (expirationDate) formData.append('expiration_date', expirationDate)

    try{
      await api.post('/documents/', formData, { headers: {'Content-Type': 'multipart/form-data'} })
      navigate('/')
    }catch(err){
      alert('Falha no upload')
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
            <label className="block text-sm font-medium text-gray-700 mb-1">Arquivo PDF</label>
            <input
              className="input w-full"
              type="file"
              accept=".pdf"
              onChange={(e)=>setFile(e.target.files[0])}
            />
          </div>

          <div className="flex justify-end pt-2">
            <button className="btn" disabled={loading}>
              {loading ? 'Enviando...' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
