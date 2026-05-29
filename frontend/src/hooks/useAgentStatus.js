/**
 * useAgentStatus — hook to poll the agent-status API.
 *
 * Returns { data, loading, error } and auto-refreshes every `intervalMs`.
 */
import { useEffect, useState, useRef, useCallback } from 'react'
import api from '../services/api'

export default function useAgentStatus(intervalMs = 5000) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const timer = useRef(null)

  const fetch = useCallback(async () => {
    try {
      const res = await api.get('/orchestrator/dashboard/agents/')
      setData(res.data)
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
    timer.current = setInterval(fetch, intervalMs)
    return () => clearInterval(timer.current)
  }, [fetch, intervalMs])

  return { data, loading, error, refetch: fetch }
}
