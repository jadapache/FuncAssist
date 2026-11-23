import { ChangeDetectionStrategy, Component, input, output } from '@angular/core'
import { Check, Eye, EyeOff, Key } from 'lucide'
import { LucideIconDirective } from '../../../../shared/icons/lucide.directive'

/**
 * Port of React `ApiKeyInput`.
 * Host is `block` because it is rendered as a direct child of a `space-y-*` container.
 */
@Component({
  selector: 'app-api-key-input',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  template: `
    <div class="space-y-1.5">
      <label class="text-xs font-bold text-slate-800 flex items-center justify-between">
        <span class="flex items-center gap-1.5">
          <svg [lucide]="icons.Key" class="h-3.5 w-3.5 text-[#002777]"></svg>
          <span>{{ label() }}</span>
        </span>
        @if (hasSavedKey() && !value()) {
          <span
            class="inline-flex items-center gap-1 text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold"
          >
            <svg [lucide]="icons.Check" class="h-3 w-3"></svg>
            <span>Configurada</span>
          </span>
        }
      </label>
      <div class="relative">
        <input
          [type]="showKey() ? 'text' : 'password'"
          [value]="value()"
          (input)="onChange.emit($any($event.target).value)"
          [placeholder]="hasSavedKey() ? '•••••••••••••••• (Deja en blanco para conservar)' : placeholder()"
          class="input-field text-xs font-mono py-2 pr-10 border border-slate-200 rounded-xl w-full"
        />
        <button
          type="button"
          (click)="setShowKey()(!showKey())"
          class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1 cursor-pointer"
        >
          @if (showKey()) {
            <svg [lucide]="icons.EyeOff" class="h-3.5 w-3.5"></svg>
          } @else {
            <svg [lucide]="icons.Eye" class="h-3.5 w-3.5"></svg>
          }
        </button>
      </div>
    </div>
  `,
})
export class ApiKeyInputComponent {
  readonly label = input.required<string>()
  readonly value = input.required<string>()
  readonly showKey = input.required<boolean>()
  readonly setShowKey = input.required<(show: boolean) => void>()
  readonly hasSavedKey = input<boolean | undefined>(undefined)
  readonly placeholder = input('sk-...')

  readonly onChange = output<string>()

  protected readonly icons = { Check, Eye, EyeOff, Key }
}
