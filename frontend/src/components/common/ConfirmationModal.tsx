import React from 'react'
import { AlertTriangle, AlertCircle, Info, Loader2, X } from 'lucide-react'

export interface ConfirmationModalProps {
  isOpen: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'warning' | 'info' | 'primary'
  isDestructive?: boolean
  isLoading?: boolean
  onConfirm: () => void | Promise<void>
  onClose: () => void
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  variant,
  isDestructive = false,
  isLoading = false,
  onConfirm,
  onClose,
}) => {
  if (!isOpen) return null

  // Determine effective variant
  const effectiveVariant = variant || (isDestructive ? 'danger' : 'primary')

  const getIcon = () => {
    switch (effectiveVariant) {
      case 'danger':
        return <AlertTriangle className="h-5 w-5 text-red-600" />
      case 'warning':
        return <AlertCircle className="h-5 w-5 text-amber-600" />
      case 'info':
        return <Info className="h-5 w-5 text-blue-600" />
      default:
        return <Info className="h-5 w-5 text-[#002777]" />
    }
  }

  const getIconBg = () => {
    switch (effectiveVariant) {
      case 'danger':
        return 'bg-red-50 ring-1 ring-red-100'
      case 'warning':
        return 'bg-amber-50 ring-1 ring-amber-100'
      case 'info':
        return 'bg-blue-50 ring-1 ring-blue-100'
      default:
        return 'bg-blue-50 ring-1 ring-blue-100'
    }
  }

  const getConfirmButtonClasses = () => {
    if (effectiveVariant === 'danger') {
      return 'bg-red-600 hover:bg-red-700 text-white shadow-xs'
    }
    if (effectiveVariant === 'warning') {
      return 'bg-amber-600 hover:bg-amber-700 text-white shadow-xs'
    }
    return 'bg-[#002777] hover:bg-[#001f5f] text-white shadow-xs'
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${getIconBg()}`}
            >
              {getIcon()}
            </div>

            <div className="flex-1 min-w-0 pt-0.5">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-base font-bold text-slate-900 leading-snug">{title}</h3>
                <button
                  type="button"
                  onClick={onClose}
                  disabled={isLoading}
                  className="text-slate-400 hover:text-slate-600 p-1 -mr-1 rounded-lg hover:bg-slate-100 transition cursor-pointer"
                  title="Cerrar"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed mt-2">{message}</p>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 bg-slate-50/80 border-t border-slate-100">
          <button
            type="button"
            disabled={isLoading}
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-xl transition cursor-pointer disabled:opacity-50"
          >
            {cancelLabel}
          </button>

          <button
            type="button"
            disabled={isLoading}
            onClick={() => void onConfirm()}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-xl transition cursor-pointer disabled:opacity-50 ${getConfirmButtonClasses()}`}
          >
            {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            <span>{confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  )
}

