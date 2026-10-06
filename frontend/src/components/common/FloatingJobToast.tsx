import React from 'react'
import {
  Download,
  Mic,
  CheckCircle2,
  AlertTriangle,
  X,
  Loader2,
} from 'lucide-react'
import type { BackgroundJobItem } from '../../context/BackgroundJobContext'

export interface FloatingJobToastProps {
  jobs?: BackgroundJobItem[]
  onCancelJob?: (id: string) => void
  onDismissJob?: (id: string) => void
}

export const FloatingJobToast: React.FC<FloatingJobToastProps> = ({
  jobs = [],
  onCancelJob,
  onDismissJob,
}) => {
  if (jobs.length === 0) {
    return null
  }

  return (
    <aside
      aria-label="Notificaciones de procesos en segundo plano"
      className="fixed top-6 right-6 z-50 flex flex-col gap-3 w-80 sm:w-96 pointer-events-auto animate-fade-in font-sans"
    >
      {jobs.map((task) => {
        const isComplete = task.status === 'complete'
        const isFailed = task.status === 'failed'
        const inProgress = !isComplete && !isFailed

        const renderIcon = () => {
          if (isComplete) {
            return <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          }
          if (isFailed) {
            return <AlertTriangle className="h-4 w-4 text-red-600" />
          }
          if (task.type === 'download') {
            return <Download className="h-4 w-4 text-slate-700 animate-pulse" />
          }
          if (task.type === 'transcription') {
            return <Mic className="h-4 w-4 text-slate-700" />
          }
          return <Loader2 className="h-4 w-4 text-slate-700 animate-spin" />
        }

        return (
          <div
            key={task.id}
            onClick={() => {
              if (task.onClick) task.onClick()
            }}
            className={[
              'bg-white border border-slate-200/90 rounded-2xl p-4 shadow-xl transition-all duration-200',
              task.onClick ? 'cursor-pointer hover:border-slate-300 hover:shadow-2xl' : '',
            ].join(' ')}
          >
            <div className="flex items-center gap-3.5">
              {/* Left Action Icon */}
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-700 shadow-2xs">
                {renderIcon()}
              </div>

              {/* Center Content */}
              <div className="flex-1 min-w-0 space-y-1.5">
                {/* Title */}
                <div className="flex items-center justify-between gap-2">
                  <h4
                    className="text-xs font-bold text-slate-900 truncate"
                    title={task.title}
                  >
                    {task.title}
                  </h4>

                  {inProgress && (task.onCancel || onCancelJob) && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (task.onCancel) task.onCancel()
                        else onCancelJob?.(task.id)
                      }}
                      className="text-[11px] font-semibold text-slate-400 hover:text-red-600 transition shrink-0 cursor-pointer"
                      title="Cancelar proceso"
                    >
                      Cancelar
                    </button>
                  )}

                  {!inProgress && (task.onDismiss || onDismissJob) && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (task.onDismiss) task.onDismiss()
                        else onDismissJob?.(task.id)
                      }}
                      className="text-slate-400 hover:text-slate-600 p-0.5 rounded transition shrink-0 cursor-pointer"
                      title="Cerrar notificación"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                {/* Horizontal Progress Bar */}
                <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden border border-slate-200/60">
                  <div
                    className={[
                      'h-full transition-all duration-300 rounded-full',
                      isComplete
                        ? 'bg-emerald-600'
                        : isFailed
                        ? 'bg-red-600'
                        : 'bg-[#002777]',
                    ].join(' ')}
                    style={{ width: `${Math.min(100, Math.max(4, task.progress))}%` }}
                  />
                </div>

                {/* Bottom Info Row: speed/size, eta, percentage */}
                <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium">
                  <span className="truncate max-w-[190px]" title={task.stageText || task.speedOrSize || ''}>
                    {task.type === 'download'
                      ? task.speedOrSize || task.stageText || `${task.progress}%`
                      : task.stageText || task.speedOrSize || `${task.progress}%`}
                  </span>

                  <div className="flex items-center gap-2 shrink-0">
                    {task.eta && inProgress && (
                      <span className="text-slate-400 font-mono text-[10px]">
                        {task.eta}
                      </span>
                    )}
                    <span className="font-bold font-mono text-slate-800">
                      {task.progress}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )
      })}
    </aside>
  )
}
export default FloatingJobToast
