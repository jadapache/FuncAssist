import { useState } from 'react'
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Database,
  Loader2,
  Square,
  XCircle,
} from 'lucide-react'
import type { AgentRunSource, AgentRunStep } from '../types/agentEvents'

export interface AgenticThinkingBubbleProps {
  status?: string
  isProcessing?: boolean
  steps?: AgentRunStep[]
  sources?: AgentRunSource[]
  onCancel?: () => void
  isCancelled?: boolean
}

export const AgenticThinkingBubble = ({
  status = 'Pensando...',
  isProcessing = true,
  steps = [],
  sources = [],
  onCancel,
  isCancelled = false,
}: AgenticThinkingBubbleProps) => {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!isProcessing && steps.length === 0 && !isCancelled) return null

  const hasTimeline = steps.length > 0 || sources.length > 0
  const toggleLabel = isExpanded ? 'Ocultar detalles' : 'Ver etapas'

  return (
    <div className="flex flex-col gap-2 p-2.5 rounded-xl bg-slate-100/90 border border-slate-200/80 text-slate-800 text-xs my-2 animate-in fade-in duration-150 max-w-xl">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {renderStatusIcon(isProcessing, isCancelled)}
          <span className="font-semibold tracking-wide">{status}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {hasTimeline && (
            <button
              type="button"
              onClick={() => setIsExpanded((prev) => !prev)}
              aria-label={toggleLabel}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
            >
              <span>{steps.length} etapas</span>
              {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          )}
          {isProcessing && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              aria-label="Cancelar generación"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium text-rose-700 hover:text-rose-800 bg-rose-50 border border-rose-200 hover:bg-rose-100 transition-colors"
            >
              <Square className="h-2.5 w-2.5 fill-rose-700 text-rose-700" />
              <span>Cancelar</span>
            </button>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="mt-2 pt-2 border-t border-slate-200/80 flex flex-col gap-2">
          <TimelineStepList steps={steps} />
          <TimelineSourcesList sources={sources} />
        </div>
      )}
    </div>
  )
}

function renderStatusIcon(isProcessing: boolean, isCancelled: boolean) {
  if (isCancelled) {
    return <XCircle className="h-4 w-4 text-rose-600" />
  }
  if (isProcessing) {
    return <Loader2 className="h-4 w-4 animate-spin text-[#002777]" />
  }
  return <CheckCircle2 className="h-4 w-4 text-emerald-600" />
}

function TimelineStepList({ steps }: { steps: AgentRunStep[] }) {
  if (steps.length === 0) return null

  return (
    <div className="flex flex-col gap-1.5 pl-1">
      {steps.map((step) => (
        <div key={step.stepId} className="flex items-start gap-2">
          {renderStepIndicator(step.status)}
          <div className="flex flex-col">
            <span
              className={`text-[11px] ${
                step.status === 'in_progress'
                  ? 'font-semibold text-slate-900'
                  : step.status === 'failed'
                  ? 'text-rose-700 font-medium'
                  : 'text-slate-600'
              }`}
            >
              {step.label}
            </span>
            {step.details && <span className="text-[10px] text-slate-500">{step.details}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function renderStepIndicator(status: AgentRunStep['status']) {
  if (status === 'completed') {
    return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 mt-0.5 flex-shrink-0" />
  }
  if (status === 'failed') {
    return <XCircle className="h-3.5 w-3.5 text-rose-600 mt-0.5 flex-shrink-0" />
  }
  return <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777] mt-0.5 flex-shrink-0" />
}

function TimelineSourcesList({ sources }: { sources: AgentRunSource[] }) {
  if (sources.length === 0) return null

  return (
    <div className="mt-1 pt-1.5 border-t border-slate-200/60">
      <div className="flex items-center gap-1.5 mb-1 text-[10px] font-semibold text-slate-500">
        <Database className="h-3 w-3 text-sky-600" />
        <span>Fuentes RAG consultadas en tiempo real:</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {sources.map((src) => (
          <span
            key={src.sourceId}
            title={src.snippet || src.title}
            className="inline-flex items-center px-1.5 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 text-[10px] font-medium max-w-[200px] truncate"
          >
            {src.title}
          </span>
        ))}
      </div>
    </div>
  )
}
