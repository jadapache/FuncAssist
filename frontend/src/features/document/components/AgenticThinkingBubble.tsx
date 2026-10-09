import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  Loader2,
} from 'lucide-react'
import type { ThinkingStep } from '../../../features/document/hooks/useChatPersistence'

interface AgenticThinkingBubbleProps {
  steps: ThinkingStep[]
  isProcessing: boolean
  /** When processing is done, the bubble auto-collapses after a short delay */
  autoCollapseMs?: number
}

/**
 * Claude-style inline thinking trace rendered inside an assistant chat bubble.
 * Shows step-by-step progress while the agent processes, then collapses when done.
 */
export const AgenticThinkingBubble = ({
  steps,
  isProcessing,
  autoCollapseMs = 2000,
}: AgenticThinkingBubbleProps) => {
  const [isExpanded, setIsExpanded] = useState(true)

  // Auto-collapse after processing finishes
  useEffect(() => {
    if (!isProcessing && steps.length > 0) {
      const timer = setTimeout(() => setIsExpanded(false), autoCollapseMs)
      return () => clearTimeout(timer)
    }
    if (isProcessing) {
      setIsExpanded(true)
    }
  }, [isProcessing, autoCollapseMs, steps.length])

  if (steps.length === 0) return null

  const completedCount = steps.filter((s) => s.status === 'completed').length
  const hasFailed = steps.some((s) => s.status === 'failed')
  const allDone = !isProcessing && steps.every((s) => s.status === 'completed' || s.status === 'failed')

  return (
    <div className="mt-1.5 mb-1">
      {/* Toggle header */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 hover:text-slate-700 transition-colors cursor-pointer group"
      >
        {isProcessing ? (
          <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
        ) : isExpanded ? (
          <ChevronDown className="h-3 w-3 text-slate-400 group-hover:text-slate-600" />
        ) : (
          <ChevronRight className="h-3 w-3 text-slate-400 group-hover:text-slate-600" />
        )}
        <span>
          {isProcessing
            ? 'Procesando...'
            : hasFailed
            ? 'Proceso completado con errores'
            : `${completedCount}/${steps.length} pasos completados`}
        </span>
      </button>

      {/* Expanded step list */}
      {isExpanded && (
        <div className="mt-1.5 ml-1 pl-3 border-l-2 border-slate-200 space-y-1 animate-in fade-in duration-150">
          {steps.map((step) => (
            <div
              key={step.id}
              className={`flex items-start gap-1.5 text-[11px] leading-tight py-0.5 ${
                step.status === 'in_progress' ? 'animate-pulse' : ''
              }`}
            >
              {/* Status icon */}
              {step.status === 'completed' && (
                <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0 mt-0.5" />
              )}
              {step.status === 'in_progress' && (
                <Clock className="h-3 w-3 text-amber-500 shrink-0 mt-0.5" />
              )}
              {step.status === 'failed' && (
                <AlertCircle className="h-3 w-3 text-rose-500 shrink-0 mt-0.5" />
              )}
              {step.status === 'pending' && (
                <div className="h-3 w-3 rounded-full border border-slate-300 shrink-0 mt-0.5" />
              )}

              <div className="min-w-0">
                <span
                  className={`font-semibold ${
                    step.status === 'completed'
                      ? 'text-emerald-700'
                      : step.status === 'failed'
                      ? 'text-rose-700'
                      : step.status === 'in_progress'
                      ? 'text-amber-700'
                      : 'text-slate-400'
                  }`}
                >
                  {step.label}
                </span>
                {step.details && (
                  <span className="text-slate-500 ml-1">— {step.details}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Collapsed summary when done */}
      {!isExpanded && allDone && !hasFailed && (
        <div className="mt-0.5 ml-1 text-[10px] text-emerald-600 flex items-center gap-1">
          <CheckCircle2 className="h-2.5 w-2.5" />
          <span>Ciclo Inspect-Plan-Execute-Verify completado</span>
        </div>
      )}
    </div>
  )
}
