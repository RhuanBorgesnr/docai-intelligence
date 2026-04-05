import React from 'react'

export default function ChatBox({messages}){
  return (
    <div className="card">
      <div className="space-y-3">
        {messages.map((m,i)=> (
          <div key={i} className={m.role==='user' ? 'text-right' : ''}>
            <div className={m.role==='user' ? 'inline-block bg-primary text-white px-4 py-2 rounded-lg' : 'inline-block bg-gray-100 px-4 py-2 rounded-lg'}>
              {m.text}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
