import type { FormEvent } from 'react'
import { useState } from 'react'
import {
  Send,
  Sparkles,
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  FileCheck,
  ChevronRight,
} from 'lucide-react'

export interface AgenticStep {
  id: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  details?: string
}

interface DocumentChatBarProps {
  onSendMessage: (message: string, attachedAssetIds: string[]) => Promise<void>
  loading: boolean
  currentSteps: AgenticStep[]
  lastFeedback: string | null
}

const DEFAULT_CHIPS = [
  'Me gustó la propuesta, incluye en las observaciones estas imágenes.',
  'Añade una recomendación sobre pruebas de carga en la solución.',
  '¿Cuáles son las secciones y etiquetas identificadas en este documento?',
]

export const DocumentChatBar = ({
  onSendMessage,
  loading,
  currentSteps,
  lastFeedback,
}: DocumentChatBarProps) => {
  const [input, setInput] = useState('')
  const [selectedAssets, setSelectedAssets] = useState<string[]>(['img_error_login', 'img_flujo_alterno'])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    const msg = input
    setInput('')
    await onSendMessage(msg, selectedAssets)
  }

  const handleChipClick = async (chip: string) => {
    if (loading) return
    setInput(chip)
  }

  const toggleAsset = (assetId: string) => {
    setSelectedAssets((prev) =>
      prev.includes(assetId) ? prev.filter((id) => id !== assetId) : [...prev, assetId]
    )
  }

  return (
    <div className="bg-white border-t border-slate-200 p-4 space-y-3 shadow-lg">
      {/* Quick Prompts Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
        <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1 shrink-0">
          <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
          Sugerencias PoC:
        </span>
        {DEFAULT_CHIPS.map((chip, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => handleChipClick(chip)}
            disabled={loading}
            className="px-3 py-1 bg-slate-100 hover:bg-indigo-50 hover:text-indigo-700 text-slate-700 rounded-full shrink-0 border border-slate-200 transition-colors cursor-pointer disabled:opacity-50"
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Asset Attachments Selector */}
      <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 p-2 rounded-xl border border-slate-100">
        <ImageIcon className="h-4 w-4 text-emerald-600 shrink-0" />
        <span className="font-semibold text-slate-700 shrink-0">Assets disponibles:</span>
        <button
          type="button"
          onClick={() => toggleAsset('img_error_login')}
          className={`px-2 py-0.5 rounded-lg border text-xs transition-colors cursor-pointer ${
            selectedAssets.includes('img_error_login')
              ? 'bg-emerald-100 text-emerald-800 border-emerald-300 font-semibold'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
          }`}
        >
          📷 img_error_login.png {selectedAssets.includes('img_error_login') ? '✓' : ''}
        </button>
        <button
          type="button"
          onClick={() => toggleAsset('img_flujo_alterno')}
          className={`px-2 py-0.5 rounded-lg border text-xs transition-colors cursor-pointer ${
            selectedAssets.includes('img_flujo_alterno')
              ? 'bg-emerald-100 text-emerald-800 border-emerald-300 font-semibold'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
          }`}
        >
          📊 img_flujo_alterno.png {selectedAssets.includes('img_flujo_alterno') ? '✓' : ''}
        </button>
        <span className="text-[11px] text-slate-500 italic ml-auto">
          ({selectedAssets.length} seleccionadas para adjuntar)
        </span>
      </div>

      {/* Agentic Execution Steps Live Trace */}
      {currentSteps.length > 0 && (
        <div className="p-3 bg-indigo-50/70 border border-indigo-100 rounded-xl space-y-1.5 animate-in fade-in duration-150">
          <div className="flex items-center justify-between text-xs font-semibold text-indigo-900 mb-1">
            <span className="flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-indigo-600" />
              Traza del Ciclo Agentic RAG + DocumentAgent:
            </span>
            {loading && <span className="text-[11px] text-indigo-600 animate-pulse">Procesando...</span>}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2">
            {currentSteps.map((step) => (
              <div
                key={step.id}
                className={`p-2 rounded-lg border text-xs flex flex-col justify-between ${
                  step.status === 'completed'
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                    : step.status === 'in_progress'
                    ? 'bg-amber-50 border-amber-200 text-amber-900 animate-pulse'
                    : step.status === 'failed'
                    ? 'bg-rose-50 border-rose-200 text-rose-900'
                    : 'bg-white/80 border-slate-200 text-slate-600'
                }`}
              >
                <div className="flex items-center gap-1 font-semibold text-[11px]">
                  {step.status === 'completed' && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />}
                  {step.status === 'in_progress' && <Clock className="h-3.5 w-3.5 text-amber-600" />}
                  {step.status === 'failed' && <AlertCircle className="h-3.5 w-3.5 text-rose-600" />}
                  {step.status === 'pending' && <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
                  <span>{step.label}</span>
                </div>
                {step.details && (
                  <span className="text-[10px] mt-1 line-clamp-1 opacity-80">{step.details}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Last Feedback Banner */}
      {lastFeedback && !loading && (
        <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2 text-xs text-emerald-900">
          <FileCheck className="h-4 w-4 text-emerald-600 shrink-0" />
          <span className="font-medium">{lastFeedback}</span>
        </div>
      )}

      {/* Prompt Input Form */}
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribe una instrucción para el documento (ej: 'Me gustó la propuesta, incluye en las observaciones estas imágenes')..."
            disabled={loading}
            className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all disabled:opacity-60 pr-10"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-5 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold flex items-center gap-2 shadow-xs transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span>Ejecutar</span>
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  )
}
