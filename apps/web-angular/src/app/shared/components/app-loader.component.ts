import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core'
import { NgTemplateOutlet } from '@angular/common'
import { Sparkles } from 'lucide'
import { LucideIconDirective } from '../icons/lucide.directive'

const SIZE_CLASSES = {
  sm: {
    container: 'h-11 w-11 rounded-xl',
    icon: 'h-5 w-5',
    ring: 'h-14 w-14',
    dot: 'h-2 w-2 -top-1 -right-1',
    text: 'text-xs',
  },
  md: {
    container: 'h-16 w-16 rounded-2xl',
    icon: 'h-8 w-8',
    ring: 'h-20 w-20',
    dot: 'h-2.5 w-2.5 -top-1 -right-1',
    text: 'text-sm',
  },
  lg: {
    container: 'h-20 w-20 rounded-3xl',
    icon: 'h-10 w-10',
    ring: 'h-24 w-24',
    dot: 'h-3 w-3 -top-1.5 -right-1.5',
    text: 'text-base',
  },
} as const

/** Branded loader (port of React `AppLoader`). */
@Component({
  selector: 'app-loader',
  imports: [LucideIconDirective, NgTemplateOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-template #content>
      <div [class]="'relative z-10 flex flex-col items-center justify-center gap-4 text-center ' + className()">
        <div class="relative flex items-center justify-center">
          <div
            [class]="'absolute ' + sizes().ring + ' rounded-full border-2 border-transparent border-t-[#004497] border-r-cyan-400 animate-spin'"
            style="animation-duration: 1.2s"
          ></div>
          <div
            [class]="'absolute ' + sizes().ring + ' rounded-full border border-slate-200/50 dark:border-slate-700/50 animate-pulse-soft'"
          ></div>
          <div
            [class]="'relative flex ' + sizes().container + ' items-center justify-center bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-xl shadow-[#002777]/35 ring-2 ring-cyan-400/30 transition-transform duration-300'"
          >
            <svg [lucide]="icons.Sparkles" [class]="sizes().icon + ' animate-pulse'"></svg>
            <span
              [class]="'absolute ' + sizes().dot + ' rounded-full bg-cyan-400 ring-2 ring-white animate-pulse-soft'"
              aria-hidden="true"
            ></span>
          </div>
        </div>

        <div class="space-y-1.5">
          <p [class]="'font-semibold text-slate-800 ' + sizes().text">{{ message() }}</p>
          @if (submessage()) {
            <p class="text-xs text-slate-500 max-w-xs mx-auto">{{ submessage() }}</p>
          }
        </div>

        <div class="h-1.5 w-36 overflow-hidden rounded-full bg-slate-200 ring-1 ring-slate-300/40">
          <div
            class="h-full w-1/2 animate-shimmer rounded-full bg-gradient-to-r from-[#002777] via-cyan-500 to-[#004497]"
            style="background-size: 200% 100%; animation: shimmer 1.5s infinite linear"
          ></div>
        </div>
      </div>
    </ng-template>

    @if (fullScreen()) {
      <div
        class="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-slate-50/90 backdrop-blur-sm p-4"
      >
        <div class="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-blue-100/60 blur-3xl"></div>
        <div class="absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-cyan-100/50 blur-3xl"></div>
        <ng-container [ngTemplateOutlet]="content" />
      </div>
    } @else {
      <div class="py-10 flex items-center justify-center">
        <ng-container [ngTemplateOutlet]="content" />
      </div>
    }
  `,
  host: { style: 'display: contents' },
})
export class AppLoaderComponent {
  readonly fullScreen = input(false)
  readonly message = input('Cargando...')
  readonly submessage = input<string | undefined>(undefined)
  readonly size = input<'sm' | 'md' | 'lg'>('md')
  readonly className = input('')

  protected readonly icons = { Sparkles }
  protected readonly sizes = computed(() => SIZE_CLASSES[this.size()])
}

/** Lightweight inline logo spinner for buttons or small widgets (port of React `LogoSpinner`). */
@Component({
  selector: 'app-logo-spinner',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div [class]="'relative inline-flex items-center justify-center ' + dims() + ' ' + className()">
      <div
        class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#004497] border-r-cyan-400 animate-spin"
      ></div>
      <svg [lucide]="icons.Sparkles" class="h-2.5 w-2.5 text-[#002777]"></svg>
    </div>
  `,
  host: { style: 'display: contents' },
})
export class LogoSpinnerComponent {
  readonly size = input<'xs' | 'sm'>('sm')
  readonly className = input('')

  protected readonly icons = { Sparkles }
  protected readonly dims = computed(() => (this.size() === 'xs' ? 'h-4 w-4' : 'h-5 w-5'))
}
