import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core'
import { PanelLeftClose, PanelLeftOpen } from 'lucide'
import { SidebarService } from '../../core/layout/sidebar.service'
import { LucideIconDirective } from '../icons/lucide.directive'

/**
 * Page title bar with sidebar toggle (port of React `PageHeader`).
 * React's `actions` prop → project content with the `actions` attribute:
 *   <app-page-header title="Inicio"><button actions>...</button></app-page-header>
 */
@Component({
  selector: 'app-page-header',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <header
      [class]="
        'flex h-14 items-center justify-between border-b border-slate-200/80 bg-white px-6 shrink-0 z-10 ' + className()
      "
    >
      <div class="flex items-center gap-3 min-w-0">
        @if (!hideSidebarToggle()) {
          <button
            type="button"
            (click)="sidebar.toggleSidebar()"
            class="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition shadow-2xs cursor-pointer shrink-0"
            [title]="sidebar.isCollapsed() ? 'Expandir menú lateral' : 'Colapsar menú lateral'"
            [attr.aria-label]="sidebar.isCollapsed() ? 'Expandir menú lateral' : 'Colapsar menú lateral'"
          >
            @if (sidebar.isCollapsed()) {
              <svg [lucide]="icons.PanelLeftOpen" class="h-4 w-4"></svg>
            } @else {
              <svg [lucide]="icons.PanelLeftClose" class="h-4 w-4"></svg>
            }
          </button>
        }

        <div class="flex items-center gap-2">
          <span class="text-slate-300 font-light text-sm" aria-hidden="true">|</span>
          <h1 class="text-sm md:text-base font-bold text-slate-800 tracking-tight truncate">{{ title() }}</h1>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <ng-content select="[actions]" />
      </div>
    </header>
  `,
})
export class PageHeaderComponent {
  readonly title = input.required<string>()
  readonly className = input('')
  readonly hideSidebarToggle = input(false)

  protected readonly sidebar = inject(SidebarService)
  protected readonly icons = { PanelLeftClose, PanelLeftOpen }
}
