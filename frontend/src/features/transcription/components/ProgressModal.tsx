import React, { useEffect, useState } from 'react'
import {
  X,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  BrainCircuit,
  Clock,
  Mic,
} from 'lucide-react'
import { useTranscriptionProgress } from '../hooks/useTranscriptionProgress'
import { transcriptionApi } from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'

interface ProgressModalProps {
  transcriptionId: string | null
  title?: string
  isOpen: boolean
  onClose: () => void
  onComplete?: () => void
}

export const ProgressModal: React.FC<ProgressModalProps> = ({
  transcriptionId,
  title,
  isOpen,
  onClose,
  onComplete,
}) => {
  const { toast } = useToast()
  const {
    progress,
    stage,
    message,
    preview,
    eta,
    modelInfo,
    isComplete,
    isFailed,
    error,
    isConnected,
  } = useTranscriptionProgress(transcriptionId)

  const [showCancelConfirm, setShowCancelConfirm] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)

  // Auto transition on complete
  useEffect(() => {
    if (isComplete) {
      const timer = setTimeout(() => {
        onComplete?.()
      }, 1200)
      return () => clearTimeout(timer)
    }
  }, [isComplete, onComplete])

  if (!isOpen || !transcriptionId) {
    return null
  }

  const stageDisplayNames: Record<string, string> = {
    uploading: 'Subiendo Grabación',
    preprocessing: 'Extrayendo Audio',
    transcribing: 'Transcribiendo con Whisper',
    diarizing: 'Identificando Interlocutores',
    summarizing: 'Generando Minuta con IA',
    finalizing: 'Guardando Entregables',
    complete: 'Transcripción Completada',
    failed: 'Error en Transcripción',
    cancelled: 'Transcripción Cancelada',
    pending: 'Iniciando Proceso...',
  }

  const handleCancel = async () => {
    if (!showCancelConfirm) {
      setShowCancelConfirm(true)
      return
    }

    setIsCancelling(true)
    try {
      await transcriptionApi.cancelTranscription(transcriptionId)
      toast.info('Transcripción cancelada y archivos temporales limpiados.')
      onClose()
    } catch (err: any) {
      toast.error(`Error al cancelar: ${err.message}`)
    } finally {
      setIsCancelling(false)
      setShowCancelConfirm(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-fade-in font-sans">
      <div className="card w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden space-y-6 p-7 animate-scale-in">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-11 w-11 items-center justify-center rounded-2xl ${
                isComplete
                  ? 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200'
                  : isFailed
                  ? 'bg-red-50 text-red-600 ring-1 ring-red-200'
                  : 'bg-blue-50 text-[#002777] ring-1 ring-blue-200'
              }`}
            >
              {isComplete ? (
                <CheckCircle2 className="h-6 w-6 text-emerald-600" />
              ) : isFailed ? (
                <AlertTriangle className="h-6 w-6 text-red-600" />
              ) : (
                <Loader2 className="h-6 w-6 animate-spin text-[#002777]" />
              )}
            </div>

            <div>
              <h3 className="text-base font-bold text-slate-900 leading-tight">
                {stageDisplayNames[stage] || stage || 'Procesando Grabación...'}
              </h3>
              <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xs font-medium">
                {title || `Reunión #${transcriptionId.slice(0, 8)}`}
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

        {/* Progress Bar and Status */}
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700 truncate pr-2">
                {message || 'Procesando audio en tiempo real...'}
              </span>
              <span className="font-bold text-[#002777] font-mono text-sm shrink-0">
                {Math.round(progress)}%
              </span>
            </div>

            <div className="h-2.5 w-full bg-slate-100 rounded-full overflow-hidden p-0.5 border border-slate-200">
              <div
                className={`h-full rounded-full transition-all duration-300 ease-out ${
                  isComplete
                    ? 'bg-emerald-600'
                    : isFailed
                    ? 'bg-red-600'
                    : 'bg-[#002777]'
                }`}
                style={{ width: `${Math.max(4, Math.min(100, progress))}%` }}
              />
            </div>
          </div>

          {/* Model info & ETA */}
          <div className="flex items-center justify-between text-xs text-slate-500">
            {modelInfo ? (
              <span className="flex items-center gap-1.5 bg-blue-50 text-[#002777] px-2.5 py-1 rounded-lg font-medium">
                <Mic className="h-3.5 w-3.5" />
                <span className="truncate max-w-[200px]">{modelInfo}</span>
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-slate-500">
                <BrainCircuit className="h-3.5 w-3.5 text-[#002777]" />
                Motor Whisper
              </span>
            )}

            {eta && !isComplete && !isFailed && (
              <span className="flex items-center gap-1 text-slate-500 font-mono">
                <Clock className="h-3.5 w-3.5 text-slate-400" />
                ETA: {eta}
              </span>
            )}
          </div>
        </div>

        {/* Reconnection Status indicator */}
        {!isConnected && !isComplete && !isFailed && (
          <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-center gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-700 shrink-0" />
            <span>Sincronizando flujo en tiempo real (SSE)...</span>
          </div>
        )}

        {/* Live Segment Preview */}
        {preview && stage === 'transcribing' && (
          <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl space-y-1 animate-fade-in">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Vista previa en tiempo real
            </p>
            <p className="text-xs text-slate-700 italic line-clamp-3">
              "{preview}"
            </p>
          </div>
        )}

        {/* Error Details */}
        {isFailed && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-2xl space-y-1 animate-fade-in">
            <div className="flex items-center gap-2 text-xs font-bold text-red-900">
              <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
              <span>Fallo en la transcripción</span>
            </div>
            <p className="text-xs text-red-700">{error || message}</p>
          </div>
        )}

        {/* Cancel Confirmation */}
        {showCancelConfirm && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-2xl space-y-2.5 animate-fade-in">
            <p className="text-xs font-bold text-red-900">¿Deseas cancelar esta transcripción?</p>
            <p className="text-[11px] text-red-700">
              Se detendrá el motor de IA y se limpiarán los archivos temporales.
            </p>
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowCancelConfirm(false)}
                disabled={isCancelling}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 rounded-xl transition"
              >
                Continuar
              </button>
              <button
                type="button"
                onClick={handleCancel}
                disabled={isCancelling}
                className="px-4 py-1.5 text-xs font-bold text-white bg-red-600 hover:bg-red-700 rounded-xl transition shadow-xs"
              >
                {isCancelling ? 'Cancelando...' : 'Sí, Cancelar'}
              </button>
            </div>
          </div>
        )}

        {/* Actions Footer */}
        <div className="pt-2 flex items-center justify-between">
          {!isComplete && !isFailed && !showCancelConfirm && (
            <>
              <span className="text-[11px] text-slate-400">
                Puedes cerrar esta ventana; el proceso continuará en segundo plano.
              </span>
              <button
                type="button"
                onClick={() => setShowCancelConfirm(true)}
                className="text-xs font-semibold text-red-600 hover:text-red-700 hover:bg-red-50 px-3 py-1.5 rounded-xl transition"
              >
                Cancelar
              </button>
            </>
          )}

          {(isComplete || isFailed) && (
            <div className="w-full flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-5 py-2 bg-[#002777] hover:bg-blue-900 text-white rounded-xl text-xs font-bold transition shadow-xs"
              >
                {isComplete ? 'Ver Transcripción' : 'Cerrar'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
