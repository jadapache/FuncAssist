import type React from 'react'
import { useState } from 'react'
import {
  X,
  Sparkles,
  Clock,
  CheckCircle2,
  AlertTriangle,
  FileAudio,
  Users,
  BrainCircuit,
  Loader2,
} from 'lucide-react'
import type { TranscriptionProgress } from '../api/transcriptionApi'

interface TranscriptionProgressModalProps {
  isOpen: boolean
  progress: TranscriptionProgress | null
  title?: string
  onClose: () => void
  onCancel: (transcriptionId: string) => Promise<void>
}

export const TranscriptionProgressModal: React.FC<TranscriptionProgressModalProps> = ({
  isOpen,
  progress,
  title,
  onClose,
  onCancel,
}) => {
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)

  if (!isOpen || !progress) return null

  const isComplete = progress.status === 'complete' || progress.progress === 100
  const isFailed = progress.status === 'failed'
  const isCancelled = progress.status === 'cancelled'

  const stages = [
    { key: 'preprocessing', label: 'Procesamiento de Audio', icon: FileAudio },
    { key: 'transcribing', label: 'Reconocimiento de Voz (Whisper)', icon: BrainCircuit },
    { key: 'diarizing', label: 'Identificación de Interlocutores', icon: Users },
    { key: 'summarizing', label: 'Resumen & Extracción de Reqs con IA', icon: Sparkles },
  ]

  const currentStage = progress.stage || progress.status || 'preprocessing'

  const getStageStatus = (stageKey: string) => {
    const stageOrder = ['preprocessing', 'transcribing', 'diarizing', 'summarizing']
    const currIdx = stageOrder.indexOf(currentStage)
    const targetIdx = stageOrder.indexOf(stageKey)

    if (isComplete) return 'completed'
    if (currIdx === targetIdx) return 'active'
    if (currIdx > targetIdx) return 'completed'
    return 'pending'
  }

  const handleCancelClick = async () => {
    if (!showCancelConfirm) {
      setShowCancelConfirm(true)
      return
    }

    try {
      setIsCancelling(true)
      await onCancel(progress.id)
      setShowCancelConfirm(false)
      onClose()
    } finally {
      setIsCancelling(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-fade-in">
      <div className="card w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden space-y-6 p-7 animate-scale-in">
        {/* Modal Header */}
        <div className="flex items-start justify-between gap-3 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className={`flex h-11 w-11 items-center justify-center rounded-2xl shadow-inner ${
              isComplete
                ? 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200'
                : isFailed || isCancelled
                ? 'bg-red-50 text-red-600 ring-1 ring-red-200'
                : 'bg-blue-50 text-[#002777] ring-1 ring-blue-200'
            }`}>
              {isComplete ? (
                <CheckCircle2 className="h-6 w-6 text-emerald-600" />
              ) : isFailed || isCancelled ? (
                <AlertTriangle className="h-6 w-6 text-red-600" />
              ) : (
                <Loader2 className="h-6 w-6 animate-spin text-[#002777]" />
              )}
            </div>

            <div>
              <h3 className="text-base font-bold text-slate-900 leading-tight">
                {isComplete
                  ? '¡Transcripción Finalizada!'
                  : isFailed
                  ? 'Error en la Transcripción'
                  : isCancelled
                  ? 'Transcripción Cancelada'
                  : 'Procesando Grabación...'}
              </h3>
              <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xs font-medium">
                {title || `Reunión #${progress.id.slice(0, 8)}`}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition"
            title="Cerrar ventana"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Progress Bar & Stage Indicator */}
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700">{progress.message || 'Procesando audio...'}</span>
              <span className="font-bold text-[#002777] font-mono text-sm">{progress.progress}%</span>
            </div>

            <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden p-0.5 border border-slate-200/60">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  isComplete
                    ? 'bg-emerald-500'
                    : isFailed || isCancelled
                    ? 'bg-red-500'
                    : 'bg-[#002777]'
                }`}
                style={{ width: `${Math.max(5, progress.progress)}%` }}
              />
            </div>
          </div>

          {/* Model info & ETA */}
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            {progress.model_info && (
              <span className="flex items-center gap-1.5 bg-slate-100 px-2.5 py-1 rounded-lg font-medium text-slate-700">
                <Sparkles className="h-3.5 w-3.5 text-[#002777]" />
                {progress.model_info}
              </span>
            )}

            {progress.eta && !isComplete && (
              <span className="flex items-center gap-1 text-slate-500 font-mono">
                <Clock className="h-3.5 w-3.5 text-slate-400" />
                ETA: {progress.eta}
              </span>
            )}
          </div>
        </div>

        {/* Workflow Stages Timeline */}
        <div className="space-y-2.5 pt-2 border-t border-slate-100">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Fases del Procesamiento
          </p>
          <div className="space-y-2">
            {stages.map((st) => {
              const status = getStageStatus(st.key)
              const Icon = st.icon

              return (
                <div
                  key={st.key}
                  className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs transition ${
                    status === 'active'
                      ? 'bg-blue-50/80 text-[#002777] font-bold ring-1 ring-blue-200 shadow-xs'
                      : status === 'completed'
                      ? 'bg-emerald-50/50 text-emerald-800 font-medium'
                      : 'text-slate-400 bg-slate-50/50'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className={`h-4 w-4 ${status === 'active' ? 'text-[#002777]' : status === 'completed' ? 'text-emerald-600' : 'text-slate-400'}`} />
                    <span>{st.label}</span>
                  </div>

                  <div>
                    {status === 'active' && <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />}
                    {status === 'completed' && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Cancellation Confirmation or Action Buttons */}
        <div className="pt-2">
          {showCancelConfirm ? (
            <div className="p-4 rounded-2xl bg-red-50 border border-red-200 space-y-3 animate-fade-in">
              <div className="flex items-center gap-2 text-xs font-bold text-red-900">
                <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
                <span>¿Cancelar transcripción en curso?</span>
              </div>
              <p className="text-[11px] text-red-700 leading-relaxed">
                Se detendrá el proceso de IA y se eliminarán los archivos temporales asociados.
              </p>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowCancelConfirm(false)}
                  disabled={isCancelling}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200/60 rounded-xl transition"
                >
                  Continuar proceso
                </button>
                <button
                  type="button"
                  onClick={handleCancelClick}
                  disabled={isCancelling}
                  className="px-4 py-1.5 text-xs font-bold text-white bg-red-600 hover:bg-red-700 rounded-xl transition shadow-xs"
                >
                  {isCancelling ? 'Cancelando...' : 'Sí, Cancelar'}
                </button>
              </div>
            </div>
          ) : !isComplete && !isFailed && !isCancelled ? (
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-500">
                Puedes cerrar este modal; el proceso continuará en segundo plano.
              </span>
              <button
                type="button"
                onClick={() => setShowCancelConfirm(true)}
                className="text-xs font-semibold text-red-600 hover:text-red-700 hover:bg-red-50 px-3 py-1.5 rounded-xl transition"
              >
                Cancelar
              </button>
            </div>
          ) : (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="btn-primary px-5 py-2 rounded-xl text-xs font-bold shadow-xs"
              >
                Entendido
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
