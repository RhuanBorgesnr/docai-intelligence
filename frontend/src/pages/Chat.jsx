   import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'

                                                                                                                                                                                                                                                                                                                                                            const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const BACKEND_BASE = API_BASE.replace(/\/api\/?$/, '')

function isPdf(filename) {
  return /\.pdf$/i.test(filename || '')
}

function isImage(filename) {
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(filename || '')
}

function DocumentViewer({ doc }) {
  const fileUrl = doc.file?.startsWith('http')
    ? doc.file
    : `${BACKEND_BASE}/${doc.file?.replace(/^\//, '')}`
  const filename = doc.file?.split('/').pop() || ''

  if (isPdf(filename)) {
    return (
      <iframe
        src={fileUrl}
        title={doc.title || filename}
        className="w-full h-[600px] border rounded-lg"
      />
    )
  }

  if (isImage(filename)) {
    return (
      <div className="flex justify-center p-4 bg-gray-50 rounded-lg">
        <img src={fileUrl} alt={doc.title || filename} className="max-w-full max-h-[600px] rounded shadow" />
      </div>
    )
  }

  // Text/Markdown/Other — show extracted text
  if (doc.extracted_text) {
    return (
      <div className="bg-gray-50 border rounded-lg p-6 max-h-[600px] overflow-y-auto">
        <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono leading-relaxed">
          {doc.extracted_text}
        </pre>
      </div>
    )
  }

  // Fallback: download link
  return (
    <div className="card text-center py-10">
      <p className="text-gray-500 mb-4">Pré-visualização não disponível para este tipo de arquivo.</p>
      <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="btn">
        Baixar Arquivo
      </a>
    </div>
  )
}

export default function Chat() {
  const { id } = useParams()
  const [doc, setDoc] = useState(null)
  const [loadingDoc, setLoadingDoc] = useState(true)
  const [tab, setTab] = useState('document') // 'document' | 'chat'
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoadingDoc(true)
    api.get(`/documents/${id}/`)
      .then(res => setDoc(res.data))
      .catch(() => setDoc(null))
      .finally(() => setLoadingDoc(false))
  }, [id])

  async function send() {
    if (!input) return
    const userMsg = { role: 'user', text: input }
    setMessages(m => [...m, userMsg])
    setInput('')
    setLoading(true)
    try {
      const res = await api.post('/chat/', { document_ids: [parseInt(id, 10)], question: userMsg.text })
      setMessages(m => [...m, { role: 'ai', text: res.data.answer, docs: res.data.documents_used }])
    } catch (err) {
      setMessages(m => [...m, { role: 'ai', text: 'Erro ao consultar o servidor.' }])
    } finally { setLoading(false) }
  }

  if (loadingDoc) {
    return <div className="p-6 text-gray-400">Carregando documento...</div>
  }

  if (!doc) {
    return (
      <div className="p-6 text-center">
        <p className="text-gray-500">Documento não encontrado.</p>
        <Link to="/app" className="text-primary hover:underline mt-2 inline-block">← Voltar</Link>
      </div>
    )
  }

  const filename = doc.file?.split('/').pop() || ''

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <Link to="/app" className="text-sm text-primary hover:underline">← Voltar</Link>
          <h1 className="text-xl font-semibold mt-1">{doc.title || filename}</h1>
          <div className="flex items-center gap-3 text-sm text-gray-500 mt-1">
            <span className="px-2 py-0.5 bg-gray-100 rounded">{doc.document_type_display || doc.document_type}</span>
            <span>{doc.processing_status}</span>
            {doc.reference_date && <span>Ref: {doc.reference_date}</span>}
            {doc.expiration_date && <span>Venc: {doc.expiration_date}</span>}
          </div>
        </div>
        {doc.file && (
          <a
            href={doc.file?.startsWith('http') ? doc.file : `${BACKEND_BASE}/${doc.file?.replace(/^\//, '')}`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn text-sm"
          >
            ⬇ Download
          </a>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b mb-4">
        <button
          onClick={() => setTab('document')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === 'document' ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
        >
          📄 Documento
        </button>
        <button
          onClick={() => setTab('chat')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === 'chat' ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
        >
          💬 Perguntar
        </button>
      </div>

      {/* Tab Content */}
      {tab === 'document' && <DocumentViewer doc={doc} />}

      {tab === 'chat' && (
        <div>
          <div className="card min-h-[240px] max-h-[400px] overflow-y-auto">
            {messages.length === 0 && (
              <p className="text-gray-400 text-sm">Faça uma pergunta sobre este documento.</p>
            )}
            <div className="space-y-4">
              {messages.map((msg, i) => (
                <div key={i} className={msg.role === 'user' ? 'text-right' : ''}>
                  <div className={msg.role === 'user' ? 'inline-block bg-primary text-white px-4 py-2 rounded-lg' : 'inline-block bg-gray-100 px-4 py-2 rounded-lg'}>
                    <div>{msg.text}</div>
                  </div>
                  {msg.docs && msg.docs.length > 0 && (
                    <div className="text-xs text-gray-500 mt-1">Trechos usados: {msg.docs.join(', ')}</div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 flex gap-3">
            <input
              className="input flex-1"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Pergunte algo sobre o documento..."
            />
            <button className="btn" onClick={send} disabled={loading}>
              {loading ? '...' : 'Enviar'}
            </button>
          </div>
        </div>
      )}

      {/* Metadata section */}
      {doc.extracted_metadata && Object.keys(doc.extracted_metadata).length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Metadados Extraídos</h3>
          <div className="card bg-gray-50">
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
              {Object.entries(doc.extracted_metadata).map(([key, val]) => (
                <div key={key}>
                  <dt className="text-gray-500 text-xs">{key}</dt>
                  <dd className="font-medium text-gray-800">{typeof val === 'object' ? JSON.stringify(val) : String(val)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </div>
  )
}
