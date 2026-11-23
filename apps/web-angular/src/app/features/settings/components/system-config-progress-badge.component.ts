import { ChangeDetectionStrategy, Component, DestroyRef, inject, input, output, signal } from '@angular/core'
import { CheckCircle2, Circle, Sliders, X } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'

export type ConfigProgressTabTarget = 'ai_providers' | 'integrations' | 'mcp' | 'personal'

export interface ConfigProgressItem {
  id: string
  label: string
  description: string
  done: boolean
  tabTarget?: ConfigProgressTabTarget
}

/**
 * Port of React `SystemConfigProgressBadge`.
 * `onNavigateTab` → output of the same name (the single React call site always passes it).
 */
@Component({
  selector: 'app-system-config-progress-badge',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="relative inline-flex" (mouseenter)="handleMouseEnter()" (mouseleave)="handleMouseLeave()">
      <button
        type="button"
        (click)="isOpen.set(!isOpen())"
        [attr.aria-expanded]="isOpen()"
        aria-haspopup="dialog"
        class="inline-flex items-center gap-2 rounded-full border border-blue-200/80 bg-blue-50/90 px-3 py-1 text-xs font-semibold text-[#002777] shadow-2xs hover:bg-blue-100 hover:border-blue-300 transition-colors cursor-pointer"
      >
        <svg [lucide]="icons.Sliders" class="h-3.5 w-3.5 text-[#002777]" aria-hidden="true"></svg>
        <span>Progreso de configuración del sistema</span>
        <span class="rounded-full bg-[#002777] px-2 py-0.5 text-[11px] font-bold text-white shadow-2xs">
          {{ progressPercentage() }}%
        </span>
      </button>

      @if (isOpen()) {
        <div
          role="dialog"
          aria-label="Detalle de progreso de configuración del sistema"
          class="absolute left-0 top-full z-50 mt-2 w-80 sm:w-96 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl ring-1 ring-black/5 animate-in fade-in zoom-in-95 duration-150"
        >
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h4 class="text-sm font-bold text-slate-900">Progreso de configuración del sistema</h4>
              <p class="text-xs text-slate-500">Estado de componentes clave del entorno</p>
            </div>
            <button
              type="button"
              (click)="isOpen.set(false)"
              class="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
              aria-label="Cerrar detalle"
            >
              <svg [lucide]="icons.X" class="h-4 w-4"></svg>
            </button>
          </div>

          <div class="mt-3.5 space-y-1.5">
            <div class="flex items-center justify-between text-xs font-medium text-slate-600">
              <span>Completitud general</span>
              <span class="font-bold text-[#002777]">{{ progressPercentage() }}%</span>
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                class="h-full rounded-full bg-gradient-to-r from-blue-600 to-cyan-500 transition-all duration-500"
                [style.width]="progressPercentage() + '%'"
              ></div>
            </div>
          </div>

          <ul class="mt-4 divide-y divide-slate-100">
            @for (item of items(); track item.id) {
              <li class="flex items-center justify-between py-2.5">
                <div class="pr-2 min-w-0">
                  <p class="text-xs font-semibold text-slate-800 truncate">{{ item.label }}</p>
                  <p class="text-[11px] text-slate-500 truncate">{{ item.description }}</p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <span
                    [class]="
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ' +
                      (item.done
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-slate-100 text-slate-600 border border-slate-200')
                    "
                  >
                    @if (item.done) {
                      <svg [lucide]="icons.CheckCircle2" class="h-3 w-3 text-emerald-600"></svg>
                    } @else {
                      <svg [lucide]="icons.Circle" class="h-3 w-3 text-slate-400"></svg>
                    }
                    {{ item.done ? 'Hecho' : 'No hecho' }}
                  </span>
                  @if (item.tabTarget && !item.done) {
                    <button
                      type="button"
                      (click)="navigate(item.tabTarget)"
                      class="text-[11px] font-medium text-blue-600 hover:text-blue-800 underline cursor-pointer"
                    >
                      Configurar
                    </button>
                  }
                </div>
              </li>
            }
          </ul>
        </div>
      }
    </div>
  `,
})
export class SystemConfigProgressBadgeComponent {
  readonly items = input.required<ConfigProgressItem[]>()
  readonly progressPercentage = input.required<number>()
  readonly onNavigateTab = output<ConfigProgressTabTarget>()

  protected readonly icons = { CheckCircle2, Circle, Sliders, X }
  protected readonly isOpen = signal(false)
  private hoverTimeout: ReturnType<typeof setTimeout> | null = null

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.hoverTimeout) clearTimeout(this.hoverTimeout)
    })
  }

  protected handleMouseEnter(): void {
    if (this.hoverTimeout) {
      clearTimeout(this.hoverTimeout)
      this.hoverTimeout = null
    }
    this.isOpen.set(true)
  }

  protected handleMouseLeave(): void {
    this.hoverTimeout = setTimeout(() => {
      this.isOpen.set(false)
    }, 250)
  }

  protected navigate(tab: ConfigProgressTabTarget): void {
    this.isOpen.set(false)
    this.onNavigateTab.emit(tab)
  }
}
