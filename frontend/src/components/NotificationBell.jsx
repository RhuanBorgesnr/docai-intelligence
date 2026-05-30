/**
 * NotificationBell — real-time notification bell for client navbar.
 * 
 * Shows document processing completions and system events via WebSocket.
 * Displays a badge count and dropdown with recent notifications.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react'
import useWebSocket from '../hooks/useWebSocket'

const MAX_NOTIFICATIONS = 20
const AUTO_DISMISS_MS = 30000

export default function NotificationBell() {
  const [notifications, setNotifications] = useState([])
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const panelRef = useRef(null)

  const handleMessage = useCallback((data) => {
    // Handle document status events
    if (data.type === 'document.status') {
      const { document_id, status, detail } = data
      if (status === 'completed' || status === 'failed') {
        const notification = {
          id: `doc-${document_id}-${Date.now()}`,
          type: status === 'completed' ? 'success' : 'error',
          icon: status === 'completed' ? '✅' : '❌',
          title: status === 'completed' ? 'Documento Processado' : 'Falha no Processamento',
          message: detail?.message || (status === 'completed' 
            ? 'Documento pronto para consultas com IA' 
            : 'Erro ao processar documento'),
          time: new Date(),
          read: false,
          documentId: document_id,
        }
        setNotifications(prev => [notification, ...prev].slice(0, MAX_NOTIFICATIONS))
        setUnread(prev => prev + 1)
      }
    }
    // Handle general notifications
    if (data.type === 'notification') {
      const notification = {
        id: `notif-${Date.now()}`,
        type: data.level || 'info',
        icon: data.level === 'error' ? '⚠️' : data.level === 'success' ? '✅' : 'ℹ️',
        title: data.title || 'Notificação',
        message: data.message || '',
        time: new Date(),
        read: false,
      }
      setNotifications(prev => [notification, ...prev].slice(0, MAX_NOTIFICATIONS))
      setUnread(prev => prev + 1)
    }
  }, [])

  // Connect to both documents and notifications WS channels
  useWebSocket('/ws/documents/', { onMessage: handleMessage })
  useWebSocket('/ws/notifications/', { onMessage: handleMessage })

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function markAllRead() {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    setUnread(0)
  }

  function clearAll() {
    setNotifications([])
    setUnread(0)
    setOpen(false)
  }

  function timeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000)
    if (seconds < 60) return 'agora'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}min`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h`
    return `${Math.floor(hours / 24)}d`
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => { setOpen(!open); if (!open) markAllRead() }}
        className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors"
        title="Notificações"
      >
        <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center w-4 h-4 text-[10px] font-bold text-white bg-red-500 rounded-full">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-gray-200 z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <span className="text-sm font-semibold text-gray-800">Notificações</span>
            {notifications.length > 0 && (
              <button onClick={clearAll} className="text-xs text-gray-400 hover:text-gray-600">
                Limpar
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="py-8 text-center">
                <span className="text-3xl">🔔</span>
                <p className="text-sm text-gray-400 mt-2">Nenhuma notificação</p>
              </div>
            ) : (
              notifications.map(n => (
                <div
                  key={n.id}
                  className={`px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition cursor-default ${
                    !n.read ? 'bg-blue-50/50' : ''
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    <span className="text-lg flex-shrink-0 mt-0.5">{n.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-800">{n.title}</span>
                        <span className="text-[10px] text-gray-400 ml-2 flex-shrink-0">{timeAgo(n.time)}</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5 truncate">{n.message}</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
