import {
  X,
  Clock,
  ChevronRight,
  Loader2,
} from 'lucide-react'
import type { TranscriptionProgress } from '../api/transcriptionApi'

interface ActiveTranscriptionItemProps {
  progress: TranscriptionProgress
  title?: string
  onOpenModal: (transcriptionId: string) => void
  onCancel: (transcriptionId: string) => Promise<void>
  isCancelling?: boolean
}

export const ActiveTranscriptionItem: React.FC<ActiveTranscriptionItemProps> = ({
  progress,
  title,
  onOpenModal,
  onCancel,
  isCancelling = false,
}) => {
  const stageLabels: Record<string, string> = {
    pending: 'En cola',
    preprocessing: 'Preparando audio',
    transcribing: 'Reconociendo voz (Whisper)',
    diarizing: 'Identificando interlocutores',
    summarizing: 'Extrayendo resumen con IA',
    complete: 'Finalizado',
    failed: 'Error',
    cancelled: 'Cancelado',
  }

  const stage = progress.stage || progress.status || 'transcribing'
  const displayStage = stageLabels[stage] || progress.message || 'Procesando...'

  return (
    <div className="card p-4.5 bg-white border border-blue-200 hover:border-blue-400 rounded-2xl shadow-xs transition space-y-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-[#002777] ring-1 ring-blue-100">
            <Loader2 className="h-5 w-5 animate-spin text-[#002777]" />
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-bold text-slate-900 truncate">
              {title || `Transcripción #${progress.id.slice(0, 8)}`}
            </h4>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
              <span className="font-semibold text-blue-700">{displayStage}</span>
              {progress.eta && (
                <>
                  <span>•</span>
                  <span className="flex items-center gap-1 text-slate-500">
                    <Clock className="h-3 w-3" /> ETA: {progress.eta}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onOpenModal(progress.id)}
            className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-[#002777] rounded-xl text-xs font-bold transition flex items-center gap-1"
          >
            <span>Ver Progreso</span>
            <ChevronRight className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={() => onCancel(progress.id)}
            disabled={isCancelling}
            className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition"
            title="Cancelar transcripción"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs text-slate-600">
          <span className="truncate">{progress.message || 'Procesando transcripción en segundo plano...'}</span>
          <span className="font-bold text-[#002777] shrink-0">{progress.progress}%</span>
        </div>
        <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#002777] rounded-full transition-all duration-500"
            style={{ width: `${Math.max(5, progress.progress)}%` }}
          />
        </div>
      </div>
    </div>
  )
}
