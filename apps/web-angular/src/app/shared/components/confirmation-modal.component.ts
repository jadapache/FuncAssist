import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core'
import { AlertCircle, AlertTriangle, Info, Loader2, X } from 'lucide'
import { LucideIconDirective } from '../icons/lucide.directive'

export type ConfirmationVariant = 'danger' | 'warning' | 'info' | 'primary'

/** Port of React `ConfirmationModal`. Outputs keep the React callback names. */
@Component({
  selector: 'app-confirmation-modal',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (isOpen()) {
      <div
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-fade-in"
        (click)="onClose.emit()"
      >
        <div
          class="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col animate-scale-in"
          (click)="$event.stopPropagation()"
        >
          <div class="p-6">
            <div class="flex items-start gap-4">
              <div [class]="'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ' + iconBg()">
                @switch (effectiveVariant()) {
                  @case ('danger') {
                    <svg [lucide]="icons.AlertTriangle" class="h-5 w-5 text-red-600"></svg>
                  }
                  @case ('warning') {
                    <svg [lucide]="icons.AlertCircle" class="h-5 w-5 text-amber-600"></svg>
                  }
                  @case ('info') {
                    <svg [lucide]="icons.Info" class="h-5 w-5 text-blue-600"></svg>
                  }
                  @default {
                    <svg [lucide]="icons.Info" class="h-5 w-5 text-[#002777]"></svg>
                  }
                }
              </div>

              <div class="flex-1 min-w-0 pt-0.5">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="text-base font-bold text-slate-900 leading-snug">{{ title() }}</h3>
                  <button
                    type="button"
                    (click)="onClose.emit()"
                    [disabled]="isLoading()"
                    class="text-slate-400 hover:text-slate-600 p-1 -mr-1 rounded-lg hover:bg-slate-100 transition cursor-pointer"
                    title="Cerrar"
                  >
                    <svg [lucide]="icons.X" class="h-4 w-4"></svg>
                  </button>
                </div>
                <p class="text-xs text-slate-600 leading-relaxed mt-2">{{ message() }}</p>
              </div>
            </div>
          </div>

          <div class="flex items-center justify-end gap-3 px-6 py-4 bg-slate-50/80 border-t border-slate-100">
            <button
              type="button"
              [disabled]="isLoading()"
              (click)="onClose.emit()"
              class="px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-xl transition cursor-pointer disabled:opacity-50"
            >
              {{ cancelLabel() }}
            </button>
            <button
              type="button"
              [disabled]="isLoading()"
              (click)="onConfirm.emit()"
              [class]="
                'inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-xl transition cursor-pointer disabled:opacity-50 ' +
                confirmClasses()
              "
            >
              @if (isLoading()) {
                <svg [lucide]="icons.Loader2" class="h-3.5 w-3.5 animate-spin"></svg>
              }
              <span>{{ confirmLabel() }}</span>
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class ConfirmationModalComponent {
  readonly isOpen = input(false)
  readonly title = input('')
  readonly message = input('')
  readonly confirmLabel = input('Confirmar')
  readonly cancelLabel = input('Cancelar')
  readonly variant = input<ConfirmationVariant | undefined>(undefined)
  readonly isDestructive = input(false)
  readonly isLoading = input(false)

  readonly onConfirm = output<void>()
  readonly onClose = output<void>()

  protected readonly icons = { AlertCircle, AlertTriangle, Info, Loader2, X }

  protected readonly effectiveVariant = computed<ConfirmationVariant>(
    () => this.variant() || (this.isDestructive() ? 'danger' : 'primary'),
  )

  protected readonly iconBg = computed(() => {
    switch (this.effectiveVariant()) {
      case 'danger':
        return 'bg-red-50 ring-1 ring-red-100'
      case 'warning':
        return 'bg-amber-50 ring-1 ring-amber-100'
      default:
        return 'bg-blue-50 ring-1 ring-blue-100'
    }
  })

  protected readonly confirmClasses = computed(() => {
    const v = this.effectiveVariant()
    if (v === 'danger') return 'bg-red-600 hover:bg-red-700 text-white shadow-xs'
    if (v === 'warning') return 'bg-amber-600 hover:bg-amber-700 text-white shadow-xs'
    return 'bg-[#002777] hover:bg-[#001f5f] text-white shadow-xs'
  })
}
