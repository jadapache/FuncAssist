import { ChangeDetectionStrategy, Component, input } from '@angular/core'

/** Port of React `StatusPill`. */
@Component({
  selector: 'app-status-pill',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <span
      [class]="
        'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ' +
        (connected()
          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
          : 'bg-slate-100 text-slate-600 border border-slate-200')
      "
    >
      <span
        [class]="'h-2 w-2 rounded-full ' + (connected() ? 'bg-emerald-500 animate-pulse-soft' : 'bg-slate-400')"
        aria-hidden="true"
      ></span>
      {{ connected() ? 'Conectado' : 'No conectado' }}
    </span>
  `,
})
export class StatusPillComponent {
  readonly connected = input.required<boolean>()
}
