import React, { useRef, useState } from 'react'
import {
  Download,
  Mic,
  CheckCircle2,
  AlertTriangle,
  X,
  Loader2,
  Ban,
  GripVertical,
  Minus,
  Maximize2,
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
  const [collapsedJobs, setCollapsedJobs] = useState<Set<string>>(new Set())
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const dragRef = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null)

  if (jobs.length === 0) {
    return null
  }

  return (
    <aside
      aria-label="Notificaciones de procesos en segundo plano"
      className="fixed top-6 right-6 z-50 flex flex-col gap-3 w-80 sm:w-96 pointer-events-auto animate-fade-in font-sans"
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
      onPointerMove={(event) => {
        if (!dragRef.current) return
        setPosition({
          x: dragRef.current.originX + event.clientX - dragRef.current.startX,
          y: dragRef.current.originY + event.clientY - dragRef.current.startY,
        })
      }}
      onPointerUp={() => { dragRef.current = null }}
      onPointerCancel={() => { dragRef.current = null }}
    >
      {jobs.map((task) => {
        const isComplete = task.status === 'complete'
        const isFailed = task.status === 'failed'
        const isCancelled = task.status === 'cancelled'
        const inProgress = !isComplete && !isFailed && !isCancelled
        const isCancelling = inProgress && Boolean(task.stageText?.toLowerCase().startsWith('cancelando'))
        const isCollapsed = collapsedJobs.has(task.id)

        const toggleCollapsed = (event: React.MouseEvent) => {
          event.stopPropagation()
          setCollapsedJobs((previous) => {
            const next = new Set(previous)
            if (next.has(task.id)) next.delete(task.id)
            else next.add(task.id)
            return next
          })
        }

        const renderIcon = () => {
          if (isComplete) {
            return <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          }
          if (isFailed) {
            return <AlertTriangle className="h-4 w-4 text-red-600" />
          }
          if (isCancelled) {
            return <Ban className="h-4 w-4 text-slate-500" />
          }
          if (task.type === 'download') {
            return <Download className="h-4 w-4 text-slate-700 animate-pulse" />
          }
          if (task.type === 'transcription') {
            return <Mic className="h-4 w-4 text-slate-700 animate-pulse" />
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
              'bg-white border border-slate-200/90 rounded-2xl shadow-xl transition-all duration-200',
              isCollapsed ? 'px-3 py-2.5' : 'p-4',
              task.onClick ? 'cursor-pointer hover:border-slate-300 hover:shadow-2xl' : '',
            ].join(' ')}
          >
            <div
              className="flex items-center gap-2"
              onPointerDown={(event) => {
                if ((event.target as HTMLElement).closest('button')) return
                dragRef.current = {
                  startX: event.clientX,
                  startY: event.clientY,
                  originX: position.x,
                  originY: position.y,
                }
                event.currentTarget.setPointerCapture?.(event.pointerId)
              }}
              style={{ cursor: 'grab', touchAction: 'none' }}
              title="Arrastrar notificación"
            >
              {/* Left Action Icon */}
              <div className={`flex shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-700 shadow-2xs ${isCollapsed ? 'h-8 w-8' : 'h-10 w-10'}`}>
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

                  <div className="flex items-center gap-1 shrink-0">
                  {inProgress && (task.onCancel || onCancelJob) && (
                    <button
                      type="button"
                      disabled={isCancelling}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (isCancelling) return
                        if (task.onCancel) task.onCancel()
                        else onCancelJob?.(task.id)
                      }}
                      className={[
                        'text-[11px] font-semibold transition shrink-0',
                        isCancelling
                          ? 'text-slate-400 cursor-not-allowed animate-pulse'
                          : 'text-slate-400 hover:text-red-600 cursor-pointer',
                      ].join(' ')}
                      title={isCancelling ? 'Cancelando proceso...' : 'Cancelar proceso'}
                    >
                      {isCancelling ? 'Cancelando...' : 'Cancelar'}
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
                  <button
                    type="button"
                    onClick={toggleCollapsed}
                    className="text-slate-400 hover:text-slate-700 p-0.5 rounded transition cursor-pointer"
                    title={isCollapsed ? 'Expandir proceso' : 'Minimizar proceso'}
                    aria-label={isCollapsed ? 'Expandir proceso' : 'Minimizar proceso'}
                  >
                    {isCollapsed ? <Maximize2 className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                  </button>
                  </div>
                </div>

                {!isCollapsed && <>
                {/* Horizontal Progress Bar */}
                <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden border border-slate-200/60">
                  <div
                    className={[
                      'h-full transition-all duration-300 rounded-full',
                      isComplete
                        ? 'bg-emerald-600'
                        : isFailed
                        ? 'bg-red-600'
                        : isCancelled || isCancelling
                        ? 'bg-slate-400'
                        : 'bg-[#002777]',
                    ].join(' ')}
                    style={{
                      width: isCancelled
                        ? '0%'
                        : `${Math.min(100, Math.max(4, task.progress))}%`,
                    }}
                  />
                </div>

                {/* Bottom Info Row: speed/size, eta, percentage */}
                <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium">
                  <span className="truncate max-w-[210px]" title={task.stageText || task.speedOrSize || ''}>
                    {task.stageText || task.speedOrSize || `${task.progress}%`}
                  </span>

                  <div className="flex items-center gap-2 shrink-0">
                    {task.eta && inProgress && !isCancelling && (
                      <span className="text-slate-400 font-mono text-[10px]">
                        {task.eta}
                      </span>
                    )}
                    {!isCancelled && !isCancelling && (
                      <span className="font-bold font-mono text-slate-800">
                        {task.progress}%
                      </span>
                    )}
                  </div>
                </div>
                </>}
              </div>
              <GripVertical className="h-4 w-4 shrink-0 text-slate-300" aria-hidden="true" />
            </div>
          </div>
        )
      })}
    </aside>
  )
}
export default FloatingJobToast
