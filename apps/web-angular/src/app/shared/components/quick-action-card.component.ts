import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core'
import { Router, RouterLink } from '@angular/router'
import type { IconNode } from 'lucide'
import { LucideIconDirective } from '../icons/lucide.directive'

/** Dashboard quick-action tile (port of React `QuickActionCard`). `to` may include a query string. */
@Component({
  selector: 'app-quick-action-card',
  imports: [RouterLink, LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <a
      [routerLink]="link().path"
      [queryParams]="link().queryParams"
      class="group relative flex flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-[#004497]/30 hover:shadow-xl hover:shadow-blue-900/10"
      [attr.aria-label]="title()"
    >
      <div
        [class]="
          'absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gradient-to-br ' +
          gradient() +
          ' opacity-10 blur-2xl transition-opacity duration-300 group-hover:opacity-20'
        "
        aria-hidden="true"
      ></div>
      <div class="flex items-start justify-between gap-3">
        <div
          [class]="
            'flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ' +
            gradient() +
            ' text-white shadow-lg transition-transform duration-300 group-hover:scale-110 group-hover:rotate-3'
          "
        >
          <svg [lucide]="icon()" class="h-6 w-6"></svg>
        </div>
        @if (badge()) {
          <span
            class="rounded-full bg-blue-50 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#002777]"
          >
            {{ badge() }}
          </span>
        }
      </div>
      <h3
        class="mt-4 text-base font-semibold text-[var(--color-ink)] transition-colors group-hover:text-[#002777]"
      >
        {{ title() }}
      </h3>
      <p class="mt-1.5 flex-1 text-sm leading-relaxed text-[var(--color-ink-muted)]">{{ description() }}</p>
      <span
        class="mt-4 inline-flex items-center gap-1 text-sm font-medium text-[#004497] opacity-0 transition-all duration-300 group-hover:opacity-100"
      >
        Open
        <svg
          class="h-4 w-4 transition-transform group-hover:translate-x-0.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </span>
    </a>
  `,
})
export class QuickActionCardComponent {
  readonly to = input.required<string>()
  readonly title = input.required<string>()
  readonly description = input.required<string>()
  readonly icon = input.required<IconNode>()
  readonly badge = input<string | undefined>(undefined)
  readonly gradient = input('from-[#002777] to-[#004497]')

  private readonly router = inject(Router)

  /** Split "/chat?new=1&skill=x" into a routerLink path + queryParams. */
  protected readonly link = computed(() => {
    const tree = this.router.parseUrl(this.to())
    const path = '/' + (tree.root.children['primary']?.segments.map((s) => s.path).join('/') ?? '')
    return { path, queryParams: tree.queryParams }
  })
}
