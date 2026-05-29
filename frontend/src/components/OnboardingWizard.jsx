import React, { useState } from 'react'
import { Link } from 'react-router-dom'

const STEPS = [
  {
    icon: '📄',
    title: 'Envie um documento',
    description: 'Faça upload de um balanço, DRE, contrato ou nota fiscal. Aceita PDF, imagem ou texto.',
    action: { label: 'Enviar Documento', to: '/app/upload' },
  },
  {
    icon: '🤖',
    title: 'Análise automática com IA',
    description: 'Nossa IA extrai indicadores financeiros, identifica cláusulas de risco e indexa o conteúdo automaticamente.',
    action: null,
  },
  {
    icon: '💬',
    title: 'Converse com seus documentos',
    description: 'Faça perguntas em linguagem natural. A IA responde baseada no conteúdo real dos seus documentos.',
    action: null,
  },
]

export default function OnboardingWizard({ onComplete }) {
  const [step, setStep] = useState(0)

  function handleNext() {
    if (step < STEPS.length - 1) {
      setStep(step + 1)
    } else {
      localStorage.setItem('docai_onboarding_complete', 'true')
      onComplete()
    }
  }

  function handleSkip() {
    localStorage.setItem('docai_onboarding_complete', 'true')
    onComplete()
  }

  const current = STEPS[step]

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
        {/* Progress */}
        <div className="flex gap-1 p-4 pb-0">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i <= step ? 'bg-primary' : 'bg-gray-200'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="p-8 text-center">
          <div className="text-6xl mb-4">{current.icon}</div>
          <h2 className="text-xl font-bold text-gray-900 mb-3">{current.title}</h2>
          <p className="text-gray-600 leading-relaxed">{current.description}</p>

          {current.action && (
            <Link
              to={current.action.to}
              onClick={handleSkip}
              className="inline-block mt-4 px-4 py-2 bg-primary/10 text-primary rounded-lg text-sm font-medium hover:bg-primary/20 transition"
            >
              {current.action.label} →
            </Link>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between p-4 border-t bg-gray-50">
          <button
            onClick={handleSkip}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Pular
          </button>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">{step + 1} de {STEPS.length}</span>
            <button
              onClick={handleNext}
              className="btn"
            >
              {step === STEPS.length - 1 ? 'Começar' : 'Próximo'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
