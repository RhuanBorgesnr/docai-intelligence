import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      const res = await api.post('/auth/login/', { username, password })
      localStorage.setItem('access_token', res.data.access)
      localStorage.setItem('refresh_token', res.data.refresh)
      navigate('/')
    } catch (err) {
      alert('Login failed')
    }
  }

  return (
    <div className="max-w-md mx-auto">
      <div className="card">
        <h3 className="text-xl font-semibold mb-2">Entrar</h3>
        <p className="text-sm text-gray-500 mb-4">Use suas credenciais para acessar a plataforma</p>
        <form onSubmit={handleSubmit}>
          <input className="input" placeholder="Username" value={username} onChange={(e)=>setUsername(e.target.value)} />
          <input className="input" placeholder="Password" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} />
          <button className="btn w-full">Login</button>
        </form>
      </div>
    </div>
  )
}
