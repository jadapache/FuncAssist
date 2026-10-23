import { Loader2 } from 'lucide-react'

interface AgenticThinkingBubbleProps {
  status?: string
  isProcessing?: boolean
  steps?: unknown[]
}

/**
 * Modern, minimalist thinking indicator inside an assistant chat bubble.
 * Replaces the obsolete 5-point Inspect-Plan-Execute-Verify checklist.
 */
export const AgenticThinkingBubble = ({
  status = 'Pensando...',
  isProcessing = true,
}: AgenticThinkingBubbleProps) => {
  if (!isProcessing) return null

  return (
    <div className="inline-flex items-center gap-2 py-1 px-2.5 rounded-xl bg-slate-200/60 text-slate-700 text-xs font-medium my-1 animate-in fade-in duration-150">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />
      <span className="animate-pulse">{status}</span>
    </div>
  )
}

