/**
 * useDocumentStatus — real-time document processing status via WebSocket.
 *
 * Connects to /ws/documents/ and provides live processing updates for all
 * company documents. Shows step-by-step progress during AI analysis.
 *
 * Usage:
 *   const { processingDocs, getDocStatus } = useDocumentStatus()
 *   // processingDocs = { [docId]: { status, step, totalSteps, message } }
 */
import { useState, useCallback } from 'react'
import useWebSocket from './useWebSocket'

const STATUS_LABELS = {
  extracting_text: 'Extraindo texto',
  chunking: 'Segmentando',
  embedding: 'Indexando',
  analyzing_financial: 'Análise financeira',
  analyzing_clauses: 'Análise de cláusulas',
  extracting_metadata: 'Extraindo metadados',
  completed: 'Concluído',
  failed: 'Falha',
}

const STATUS_PROGRESS = {
  extracting_text: 25,
  chunking: 50,
  embedding: 75,
  analyzing_financial: 90,
  analyzing_clauses: 90,
  extracting_metadata: 90,
  completed: 100,
  failed: 0,
}

export default function useDocumentStatus() {
  const [processingDocs, setProcessingDocs] = useState({})

  const handleMessage = useCallback((data) => {
    if (data.type === 'document.status') {
      const { document_id, status, detail } = data

      if (status === 'completed' || status === 'failed') {
        // Remove after 5 seconds (let animation finish)
        setProcessingDocs(prev => ({
          ...prev,
          [document_id]: { status, ...detail, label: STATUS_LABELS[status], progress: STATUS_PROGRESS[status] }
        }))
        setTimeout(() => {
          setProcessingDocs(prev => {
            const next = { ...prev }
            delete next[document_id]
            return next
          })
        }, 5000)
      } else {
        setProcessingDocs(prev => ({
          ...prev,
          [document_id]: {
            status,
            ...detail,
            label: STATUS_LABELS[status] || status,
            progress: STATUS_PROGRESS[status] || 0,
          }
        }))
      }
    }
  }, [])

  const { connected } = useWebSocket('/ws/documents/', { onMessage: handleMessage })

  const getDocStatus = useCallback((docId) => {
    return processingDocs[docId] || null
  }, [processingDocs])

  return { processingDocs, getDocStatus, connected }
}
