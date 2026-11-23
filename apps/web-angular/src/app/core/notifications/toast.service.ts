import { Injectable, signal } from '@angular/core'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  message: string
  title?: string
  duration?: number
  count?: number
}

export const DEFAULT_TOAST_DURATIONS: Record<ToastType, number> = {
  success: 4000,
  info: 4000,
  warning: 6000,
  error: 7000,
}

/**
 * Angular port of React `ToastContext`.
 * Usage mirrors React: `inject(ToastService).toast.success('msg', 'title')`.
 */
@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([])

  readonly toast = {
    success: (message: string, title?: string, duration?: number) =>
      this.showToast({ type: 'success', message, title, duration }),
    error: (message: string, title?: string, duration?: number) =>
      this.showToast({ type: 'error', message, title, duration }),
    warning: (message: string, title?: string, duration?: number) =>
      this.showToast({ type: 'warning', message, title, duration }),
    info: (message: string, title?: string, duration?: number) =>
      this.showToast({ type: 'info', message, title, duration }),
    dismiss: (id: string) => this.dismissToast(id),
  }

  dismissToast(id: string): void {
    this.toasts.update((prev) => prev.filter((t) => t.id !== id))
  }

  showToast({ type, message, title, duration }: Omit<Toast, 'id'>): string {
    const actualDuration = duration || DEFAULT_TOAST_DURATIONS[type] || 4000
    const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

    this.toasts.update((prev) => {
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
      const newToast: Toast = { id, type, message, title, duration: actualDuration, count: 1 }
      // Limit visible toasts to max 3 simultaneous cards to prevent UI blockage
      return [...prev, newToast].slice(-3)
    })

    return id
  }
}
