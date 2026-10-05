import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  message: string
  title?: string
  duration?: number
  count?: number
}

interface ToastContextValue {
  toasts: Toast[]
  showToast: (toast: Omit<Toast, 'id'>) => string
  dismissToast: (id: string) => void
  toast: {
    success: (message: string, title?: string, duration?: number) => string
    error: (message: string, title?: string, duration?: number) => string
    warning: (message: string, title?: string, duration?: number) => string
    info: (message: string, title?: string, duration?: number) => string
    dismiss: (id: string) => void
  }
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

export const DEFAULT_TOAST_DURATIONS: Record<ToastType, number> = {
  success: 4000,
  info: 4000,
  warning: 6000,
  error: 7000,
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const showToast = useCallback(
    ({ type, message, title, duration }: Omit<Toast, 'id'>) => {
      const actualDuration = duration || DEFAULT_TOAST_DURATIONS[type] || 4000
      const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

      setToasts((prev) => {
        // Group & stack duplicates (same type, title, and message)
        const existingIdx = prev.findIndex(
          (t) => t.type === type && t.message === message && (t.title || '') === (title || ''),
        )

        if (existingIdx !== -1) {
          const updated = [...prev]
          const existing = updated[existingIdx]
          updated[existingIdx] = {
            ...existing,
            id, // Refresh ID to restart countdown timer
            count: (existing.count || 1) + 1,
            duration: actualDuration,
          }
          return updated
        }

        const newToast: Toast = {
          id,
          type,
          message,
          title,
          duration: actualDuration,
          count: 1,
        }

        // Limit visible toasts to max 3 simultaneous cards to prevent UI blockage
        const nextToasts = [...prev, newToast]
        return nextToasts.slice(-3)
      })

      return id
    },
    [],
  )

  const toastHelpers = useMemo(
    () => ({
      success: (message: string, title?: string, duration?: number) =>
        showToast({ type: 'success', message, title, duration }),
      error: (message: string, title?: string, duration?: number) =>
        showToast({ type: 'error', message, title, duration }),
      warning: (message: string, title?: string, duration?: number) =>
        showToast({ type: 'warning', message, title, duration }),
      info: (message: string, title?: string, duration?: number) =>
        showToast({ type: 'info', message, title, duration }),
      dismiss: dismissToast,
    }),
    [showToast, dismissToast],
  )

  const value = useMemo(
    () => ({
      toasts,
      showToast,
      dismissToast,
      toast: toastHelpers,
    }),
    [toasts, showToast, dismissToast, toastHelpers],
  )

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
}

export const useToast = (): ToastContextValue => {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}
