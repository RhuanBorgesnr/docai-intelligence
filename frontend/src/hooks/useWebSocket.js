/**
 * useWebSocket — generic WebSocket hook with auto-reconnect and JWT auth.
 *
 * Usage:
 *   const { lastMessage, connected, send } = useWebSocket('/ws/dashboard/')
 *   const { lastMessage } = useWebSocket('/ws/events/')
 *   const { lastMessage } = useWebSocket('/ws/agents/')
 *   const { lastMessage } = useWebSocket('/ws/notifications/')
 */
import { useEffect, useRef, useState, useCallback } from 'react'

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const RECONNECT_DELAY_MS = 3000
const MAX_RECONNECT_ATTEMPTS = 10

export default function useWebSocket(path, { onMessage, autoReconnect = true } = {}) {
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState(null)
  const wsRef = useRef(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimer = useRef(null)
  const unmounted = useRef(false)

  const getUrl = useCallback(() => {
    const token = localStorage.getItem('access_token')
    const base = `${WS_BASE}${path}`
    return token ? `${base}?token=${token}` : base
  }, [path])

  const connect = useCallback(() => {
    if (unmounted.current) return

    const url = getUrl()
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      reconnectAttempts.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setLastMessage(data)
        if (onMessage) onMessage(data)
      } catch {
        setLastMessage(event.data)
      }
    }

    ws.onclose = (event) => {
      setConnected(false)
      wsRef.current = null

      if (
        autoReconnect &&
        !unmounted.current &&
        event.code !== 4001 && // Auth rejected
        reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS
      ) {
        reconnectAttempts.current += 1
        const delay = RECONNECT_DELAY_MS * Math.min(reconnectAttempts.current, 5)
        reconnectTimer.current = setTimeout(connect, delay)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [getUrl, autoReconnect, onMessage])

  const send = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
    }
    if (wsRef.current) {
      wsRef.current.close(1000)
      wsRef.current = null
    }
  }, [])

  useEffect(() => {
    unmounted.current = false
    connect()

    return () => {
      unmounted.current = true
      disconnect()
    }
  }, [connect, disconnect])

  return { connected, lastMessage, send, disconnect, reconnect: connect }
}
