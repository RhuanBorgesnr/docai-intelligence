import React from 'react'

/**
 * ProcessingBadge — Shows real-time document processing status.
 * Animates through stages with a progress bar.
 */
export default function ProcessingBadge({ status }) {
  if (!status) return null

  const isActive = status.status !== 'completed' && status.status !== 'failed'
  const isFailed = status.status === 'failed'

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium ${
      isFailed 
        ? 'bg-red-50 text-red-700 border border-red-200'
        : isActive
          ? 'bg-blue-50 text-blue-700 border border-blue-200'
          : 'bg-green-50 text-green-700 border border-green-200'
    }`}>
      {isActive && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
        </span>
      )}
      {!isActive && !isFailed && <span>✓</span>}
      {isFailed && <span>✕</span>}
      <span>{status.message || status.label}</span>
      {isActive && status.progress > 0 && (
        <div className="w-16 bg-blue-200 rounded-full h-1 ml-1">
          <div 
            className="bg-blue-500 h-1 rounded-full transition-all duration-700"
            style={{ width: `${status.progress}%` }}
          />
        </div>
      )}
    </div>
  )
}

/**
 * ProcessingOverlay — Full-width processing indicator shown at top of Dashboard.
 * Shows all documents currently being processed.
 */
export function ProcessingPanel({ processingDocs }) {
  const docs = Object.entries(processingDocs)
  if (docs.length === 0) return null

  return (
    <div className="mb-4 space-y-2">
      {docs.map(([docId, status]) => {
        const isActive = status.status !== 'completed' && status.status !== 'failed'
        return (
          <div key={docId} className={`rounded-lg border px-4 py-3 flex items-center gap-3 transition-all ${
            status.status === 'failed'
              ? 'bg-red-50 border-red-200'
              : status.status === 'completed'
                ? 'bg-green-50 border-green-200'
                : 'bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200'
          }`}>
            {isActive && (
              <div className="flex-shrink-0">
                <svg className="animate-spin h-5 w-5 text-blue-500" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
              </div>
            )}
            {status.status === 'completed' && <span className="text-green-500 text-lg">✓</span>}
            {status.status === 'failed' && <span className="text-red-500 text-lg">✕</span>}
            
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">
                  {status.message || status.label}
                </span>
                {isActive && status.step && (
                  <span className="text-xs text-gray-400">
                    Etapa {status.step}/{status.total_steps}
                  </span>
                )}
              </div>
              {isActive && (
                <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                  <div 
                    className="bg-gradient-to-r from-blue-500 to-indigo-500 h-1.5 rounded-full transition-all duration-1000 ease-out"
                    style={{ width: `${status.progress}%` }}
                  />
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
