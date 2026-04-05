import React, { useState } from 'react'
import { useParams } from 'react-router-dom'
import api from '../services/api'

export default function Chat(){
  const { id } = useParams()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  async function send(){
    if(!input) return
    const userMsg = { role: 'user', text: input }
    setMessages((m)=>[...m, userMsg])
    setInput('')
    setLoading(true)
    try{
      const res = await api.post('/chat/', { document_ids: [parseInt(id,10)], question: userMsg.text })
      setMessages((m)=>[...m, { role: 'ai', text: res.data.answer, docs: res.data.documents_used }])
    }catch(err){
      setMessages((m)=>[...m, { role: 'ai', text: 'Erro ao consultar o servidor.' }])
    }finally{ setLoading(false) }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-semibold">Chat (doc {id})</h3>
      </div>

      <div className="card min-h-[240px]">
        <div className="space-y-4">
          {messages.map((msg,i)=> (
            <div key={i} className={msg.role === 'user' ? 'text-right' : ''}>
              <div className={msg.role === 'user' ? 'inline-block bg-primary text-white px-4 py-2 rounded-lg' : 'inline-block bg-gray-100 px-4 py-2 rounded-lg'}>
                <strong className="sr-only">{msg.role}</strong>
                <div>{msg.text}</div>
              </div>
              {msg.docs && msg.docs.length>0 && (
                <div className="text-xs text-gray-500 mt-1">Trechos usados: {msg.docs.join(', ')}</div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 flex gap-3">
        <input className="input flex-1" value={input} onChange={(e)=>setInput(e.target.value)} placeholder="Pergunte algo..." />
        <button className="btn" onClick={send} disabled={loading}>{loading? '...' : 'Enviar'}</button>
      </div>
    </div>
  )
}
