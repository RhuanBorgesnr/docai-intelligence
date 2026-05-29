/**
 * useRealtimeDashboard — real-time dashboard metrics via WebSocket.
 *
 * Falls back to polling if WebSocket is unavailable.
 * Replaces the interval-based polling in operations dashboard.
 */
import { useEffect, useState, useCallback } from 'react'
import useWebSocket from './useWebSocket'
import api from '../services/api'

export function useRealtimeDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const handleMessage = useCallback((msg) => {
    if (msg?.type === 'dashboard.update') {
      setData(msg.data)
      setLoading(false)
    } else if (msg?.type === 'dashboard.snapshot') {
      setData(msg.data)
      setLoading(false)
    }
  }, [])

  const { connected, send } = useWebSocket('/ws/dashboard/', { onMessage: handleMessage })

  // Request snapshot on connect
  useEffect(() => {
    if (connected) {
      send({ type: 'request_snapshot' })
    }
  }, [connected, send])

  // Fallback: initial fetch via REST if WS not ready
  useEffect(() => {
    if (!connected) {
      api.get('/orchestrator/dashboard/summary/')
        .then(res => { setData(res.data); setLoading(false) })
        .catch(() => setLoading(false))
    }
  }, [connected])

  return { data, loading, connected }
}

/**
 * useRealtimeEvents — live stream of case events.
 */
export function useRealtimeEvents(maxEvents = 50) {
  const [events, setEvents] = useState([])

  const handleMessage = useCallback((msg) => {
    if (msg?.type === 'case.event') {
      setEvents(prev => [msg, ...prev].slice(0, maxEvents))
    }
  }, [maxEvents])

  const { connected } = useWebSocket('/ws/events/', { onMessage: handleMessage })

  return { events, connected }
}

/**
 * useRealtimeAgents — live agent status updates.
 */
export function useRealtimeAgents() {
  const [agents, setAgents] = useState({})

  const handleMessage = useCallback((msg) => {
    if (msg?.type === 'agent.status') {
      setAgents(prev => ({
        ...prev,
        [msg.agent]: { status: msg.status, detail: msg.detail, updatedAt: new Date() },
      }))
    }
  }, [])

  const { connected } = useWebSocket('/ws/agents/', { onMessage: handleMessage })

  return { agents, connected }
}

/**
 * useRealtimeNotifications — per-user notification stream.
 */
export function useRealtimeNotifications() {
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)

  const handleMessage = useCallback((msg) => {
    if (msg?.type === 'notification') {
      setNotifications(prev => [msg, ...prev].slice(0, 100))
      setUnreadCount(prev => prev + 1)
    }
  }, [])

  const { connected, send } = useWebSocket('/ws/notifications/', { onMessage: handleMessage })

  const acknowledge = useCallback((notificationId) => {
    send({ type: 'ack', notification_id: notificationId })
    setUnreadCount(prev => Math.max(0, prev - 1))
  }, [send])

  const clearUnread = useCallback(() => setUnreadCount(0), [])

  return { notifications, unreadCount, connected, acknowledge, clearUnread }
}
