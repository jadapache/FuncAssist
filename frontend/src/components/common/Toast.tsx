import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertCircle, AlertTriangle, CheckCircle2, Sparkles, X } from 'lucide-react'
import { useToast, type Toast } from '../../context/ToastContext'

const TOAST_ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Sparkles,
}

const TOAST_STYLES = {
  success: {
    container: 'border-emerald-200/90 bg-white/95 text-emerald-950 shadow-emerald-900/10',
    iconBg: 'bg-emerald-100 text-emerald-600',
    bar: 'bg-emerald-500',
    defaultTitle: 'Operación Exitosa',
  },
  error: {
    container: 'border-red-200/90 bg-white/95 text-red-950 shadow-red-900/10',
    iconBg: 'bg-red-100 text-red-600',
    bar: 'bg-red-500',
    defaultTitle: 'Error del Sistema',
  },
  warning: {
    container: 'border-amber-200/90 bg-white/95 text-amber-950 shadow-amber-900/10',
    iconBg: 'bg-amber-100 text-amber-600',
    bar: 'bg-amber-500',
    defaultTitle: 'Advertencia',
  },
  info: {
    container: 'border-blue-200/90 bg-white/95 text-slate-900 shadow-blue-900/10',
    iconBg: 'bg-gradient-to-br from-[#002777] to-[#004497] text-white',
    bar: 'bg-[#002777]',
    defaultTitle: 'Información',
  },
}

interface ToastItemProps {
  toast: Toast
  onDismiss: (id: string) => void
}

export const ToastItem: React.FC<ToastItemProps> = ({ toast, onDismiss }) => {
  const duration = toast.duration || 10000
  const [isPaused, setIsPaused] = useState(false)
  const [progress, setProgress] = useState(100)
  const remainingTimeRef = useRef(duration)
  const lastTickRef = useRef<number>(Date.now())

  useEffect(() => {
    remainingTimeRef.current = duration
    setProgress(100)
    lastTickRef.current = Date.now()

    const interval = setInterval(() => {
      if (isPaused) {
        lastTickRef.current = Date.now()
        return
      }

      const now = Date.now()
      const delta = now - lastTickRef.current
      lastTickRef.current = now

      remainingTimeRef.current -= delta

      if (remainingTimeRef.current <= 0) {
        clearInterval(interval)
        onDismiss(toast.id)
      } else {
        const percent = Math.max(0, (remainingTimeRef.current / duration) * 100)
        setProgress(percent)
      }
    }, 50)

    return () => clearInterval(interval)
  }, [toast.id, toast.count, duration, isPaused, onDismiss])

  const style = TOAST_STYLES[toast.type]
  const Icon = TOAST_ICONS[toast.type]
  const title = toast.title || style.defaultTitle

  return (
    <div
      role="alert"
      aria-live="assertive"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => {
        lastTickRef.current = Date.now()
        setIsPaused(false)
      }}
      className={`pointer-events-auto relative overflow-hidden rounded-2xl border p-4 shadow-xl backdrop-blur-md transition-all duration-300 hover:shadow-2xl hover:scale-[1.01] ${style.container}`}
    >
      <div className="flex items-start gap-3.5">
        {/* Type Icon */}
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-sm ${style.iconBg}`}>
          <Icon className="h-5 w-5" aria-hidden />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1 pt-0.5 space-y-0.5">
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-900 leading-tight">
              {title}
            </p>
            {toast.count && toast.count > 1 ? (
              <span className="inline-flex items-center rounded-full bg-slate-900/90 px-2 py-0.5 text-[10px] font-extrabold text-white shadow-sm shrink-0">
                x{toast.count}
              </span>
            ) : null}
          </div>
          <p className="text-xs text-slate-600 leading-relaxed break-words">
            {toast.message}
          </p>
        </div>

        {/* Dismiss Button */}
        <button
          type="button"
          onClick={() => onDismiss(toast.id)}
          className="shrink-0 -mr-1 -mt-1 p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition cursor-pointer"
          aria-label="Cerrar notificación"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 10-Second Countdown Progress Bar */}
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-100/80 overflow-hidden">
        <div
          className={`h-full transition-all duration-75 ease-linear ${style.bar}`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}

export const ToastContainer: React.FC = () => {
  const { toasts, dismissToast } = useToast()

  if (typeof document === 'undefined') return null

  return createPortal(
    <aside
      aria-label="Notificaciones del sistema"
      className="fixed bottom-5 right-5 z-[99999] flex flex-col gap-2.5 pointer-events-none max-w-sm w-[calc(100vw-2.5rem)]"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={dismissToast} />
      ))}
    </aside>,
    document.body,
  )
}
