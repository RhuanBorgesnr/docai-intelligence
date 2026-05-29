/**
 * useJarvis — hook to fetch briefing and ask questions to Jarvis.
 */
import { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

export default function useJarvis() {
  const [briefing, setBriefing] = useState(null)
  const [loadingBriefing, setLoadingBriefing] = useState(true)
  const [error, setError] = useState(null)

  const fetchBriefing = useCallback(async () => {
    setLoadingBriefing(true)
    try {
      const res = await api.get('/orchestrator/jarvis/briefing/')
      setBriefing(res.data)
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoadingBriefing(false)
    }
  }, [])

  useEffect(() => {
    fetchBriefing()
  }, [fetchBriefing])

  const ask = useCallback(async (question) => {
    const res = await api.post('/orchestrator/jarvis/ask/', { question })
    return res.data
  }, [])

  return { briefing, loadingBriefing, error, refetchBriefing: fetchBriefing, ask }
}
