import { ChangeDetectionStrategy, Component, DestroyRef, inject, input, output, signal } from '@angular/core'
import { AlertTriangle, Check, Copy, FileText, RefreshCw } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'

/**
 * Port of React `UniverErrorBoundary`.
 *
 * Angular has no error boundaries: the guarded subtree reports its render/parse errors through `captureError()`
 * (see `UniverContainerComponent`), which switches this component to the same fallback view. The owner removes the
 * guarded subtree while `hasError()` is true, so "Restaurar Vista Visual" re-mounts it with fresh state, exactly
 * like the React boundary re-rendering its children.
 *
 * `onSwitchToCodeMode` is optional in React and its button only renders when the callback is provided; here that
 * is expressed with the `showSwitchToCodeMode` input.
 */
@Component({
  selector: 'app-univer-error-boundary',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (hasError()) {
      <div
        class="p-8 m-4 bg-white border border-red-200 rounded-2xl shadow-xl max-w-2xl mx-auto space-y-4 text-slate-800 animate-fadeIn font-sans"
      >
        <div class="flex items-start gap-3.5">
          <div class="p-2.5 bg-red-100 text-red-700 rounded-xl shrink-0">
            <svg [lucide]="icons.AlertTriangle" class="h-6 w-6"></svg>
          </div>
          <div class="space-y-1">
            <h3 class="font-bold text-base text-slate-900">
              Se detectó una inconsistencia en la vista visual del documento
            </h3>
            <p class="text-xs text-slate-600 leading-relaxed">
              El componente visual previno un cierre inesperado. Tu contenido está totalmente a salvo y no se ha perdido información.
            </p>
          </div>
        </div>

        @if (error()?.message) {
          <div
            class="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 overflow-x-auto max-h-28"
          >{{ error()?.message }}</div>
        }

        <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
          <button
            type="button"
            (click)="handleReset()"
            class="px-3.5 py-1.5 bg-[#002777] hover:bg-[#003399] text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer shadow-xs"
          >
            <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5"></svg>
            <span>Restaurar Vista Visual</span>
          </button>

          @if (showSwitchToCodeMode()) {
            <button
              type="button"
              (click)="handleReset(); onSwitchToCodeMode.emit()"
              class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <svg [lucide]="icons.FileText" class="h-3.5 w-3.5 text-[#002777]"></svg>
              <span>Editar en Modo Código Markdown</span>
            </button>
          }

          @if (fallbackContent()) {
            <button
              type="button"
              (click)="handleCopyFallback()"
              class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ml-auto"
            >
              @if (copied()) {
                <svg [lucide]="icons.Check" class="h-3.5 w-3.5 text-emerald-600"></svg>
              } @else {
                <svg [lucide]="icons.Copy" class="h-3.5 w-3.5"></svg>
              }
              <span>{{ copied() ? '¡Copiado!' : 'Copiar Texto Respaldo' }}</span>
            </button>
          }
        </div>
      </div>
    } @else {
      <ng-content />
    }
  `,
})
export class UniverErrorBoundaryComponent {
  readonly fallbackContent = input<string | undefined>(undefined)
  /** React rendered the "Editar en Modo Código Markdown" button only when `onSwitchToCodeMode` was provided. */
  readonly showSwitchToCodeMode = input<boolean>(false)
  readonly onSwitchToCodeMode = output<void>()
  readonly onRecover = output<void>()

  protected readonly icons = { AlertTriangle, RefreshCw, Copy, Check, FileText }

  readonly hasError = signal(false)
  readonly error = signal<Error | null>(null)
  readonly copied = signal(false)

  private copiedTimer: ReturnType<typeof setTimeout> | null = null

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.copiedTimer) clearTimeout(this.copiedTimer)
    })
  }

  /** Equivalent of `getDerivedStateFromError` + `componentDidCatch`. */
  captureError(error: unknown): void {
    const normalized = error instanceof Error ? error : new Error(String(error))
    console.error('UniverContainer error caught by boundary:', normalized)
    this.hasError.set(true)
    this.error.set(normalized)
    this.copied.set(false)
  }

  protected handleReset(): void {
    this.hasError.set(false)
    this.error.set(null)
    this.onRecover.emit()
  }

  protected handleCopyFallback(): void {
    const fallbackContent = this.fallbackContent()
    if (fallbackContent) {
      void navigator.clipboard.writeText(fallbackContent)
      this.copied.set(true)
      if (this.copiedTimer) clearTimeout(this.copiedTimer)
      this.copiedTimer = setTimeout(() => this.copied.set(false), 2000)
    }
  }
}
