import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, input, output, signal } from '@angular/core'
import { AlertCircle, AlertTriangle, CheckCircle2, Sparkles, X } from 'lucide'
import { ToastService, type Toast } from '../../core/notifications/toast.service'
import { LucideIconDirective } from '../icons/lucide.directive'

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

/** Single toast card with pause-on-hover countdown (port of React `ToastItem`). */
@Component({
  selector: 'app-toast-item',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div
      role="alert"
      aria-live="assertive"
      (mouseenter)="isPaused = true"
      (mouseleave)="resume()"
      [class]="
        'pointer-events-auto relative overflow-hidden rounded-2xl border p-4 shadow-xl backdrop-blur-md transition-all duration-300 hover:shadow-2xl hover:scale-[1.01] ' +
        style().container
      "
    >
      <div class="flex items-start gap-3.5">
        <div [class]="'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-sm ' + style().iconBg">
          <svg [lucide]="icon()" class="h-5 w-5"></svg>
        </div>

        <div class="min-w-0 flex-1 pt-0.5 space-y-0.5">
          <div class="flex items-center gap-2">
            <p class="text-xs font-bold uppercase tracking-wider text-slate-900 leading-tight">
              {{ toast().title || style().defaultTitle }}
            </p>
            @if (toast().count && toast().count! > 1) {
              <span
                class="inline-flex items-center rounded-full bg-slate-900/90 px-2 py-0.5 text-[10px] font-extrabold text-white shadow-sm shrink-0"
              >
                x{{ toast().count }}
              </span>
            }
          </div>
          <p class="text-xs text-slate-600 leading-relaxed break-words">{{ toast().message }}</p>
        </div>

        <button
          type="button"
          (click)="onDismiss.emit(toast().id)"
          class="shrink-0 -mr-1 -mt-1 p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition cursor-pointer"
          aria-label="Cerrar notificación"
        >
          <svg [lucide]="icons.X" class="h-4 w-4"></svg>
        </button>
      </div>

      <div class="absolute bottom-0 left-0 right-0 h-1 bg-slate-100/80 overflow-hidden">
        <div [class]="'h-full transition-all duration-75 ease-linear ' + style().bar" [style.width.%]="progress()"></div>
      </div>
    </div>
  `,
})
export class ToastItemComponent {
  readonly toast = input.required<Toast>()
  readonly onDismiss = output<string>()

  protected readonly icons = { X }
  protected readonly progress = signal(100)
  protected isPaused = false

  private remaining = 0
  private lastTick = Date.now()
  private interval: ReturnType<typeof setInterval> | null = null

  protected style = () => TOAST_STYLES[this.toast().type]
  protected icon = () => TOAST_ICONS[this.toast().type]

  constructor() {
    // Restart the countdown whenever the toast is refreshed (new id / stacked count).
    effect(() => {
      const t = this.toast()
      const duration = t.duration || 10000
      this.remaining = duration
      this.progress.set(100)
      this.lastTick = Date.now()
      if (this.interval) clearInterval(this.interval)
      this.interval = setInterval(() => {
        if (this.isPaused) {
          this.lastTick = Date.now()
          return
        }
        const now = Date.now()
        this.remaining -= now - this.lastTick
        this.lastTick = now
        if (this.remaining <= 0) {
          if (this.interval) clearInterval(this.interval)
          this.onDismiss.emit(t.id)
        } else {
          this.progress.set(Math.max(0, (this.remaining / duration) * 100))
        }
      }, 50)
    })
    inject(DestroyRef).onDestroy(() => {
      if (this.interval) clearInterval(this.interval)
    })
  }

  protected resume(): void {
    this.lastTick = Date.now()
    this.isPaused = false
  }
}

/** Global toast stack, bottom-right (port of React `ToastContainer`). */
@Component({
  selector: 'app-toast-container',
  imports: [ToastItemComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <aside
      aria-label="Notificaciones del sistema"
      class="fixed bottom-5 right-5 z-[99999] flex flex-col gap-2.5 pointer-events-none max-w-sm w-[calc(100vw-2.5rem)]"
    >
      @for (toast of toastService.toasts(); track toast.id) {
        <app-toast-item [toast]="toast" (onDismiss)="toastService.dismissToast($event)" />
      }
    </aside>
  `,
})
export class ToastContainerComponent {
  protected readonly toastService = inject(ToastService)
}
