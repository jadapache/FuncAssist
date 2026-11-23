import { ChangeDetectionStrategy, Component, OnInit, input, output, signal } from '@angular/core'
import { api } from '../../../api/client'

type JiraProject = {
  id: string
  key: string
  name: string
  selected: boolean
}

/**
 * Port of React `JiraProjectsPanel`.
 * The host IS the React root `<div>` (classes on the host) because the component is a direct child of a
 * `space-y-4` container in IntegrationCard.
 */
@Component({
  selector: 'app-jira-projects-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'mt-5 space-y-4 border-t border-[var(--color-border)] pt-5',
    style: 'display: block',
  },
  template: `
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold">Jira projects</h3>
        <p class="mt-1 text-xs text-[var(--color-ink-muted)]">
          Features use issues from selected projects only. On connect, we try to match your site URL@if (siteUrl()) {
            (<code class="text-[10px]">{{ siteUrl() }}</code>)}.
        </p>
      </div>
      <button
        type="button"
        [disabled]="busy()"
        (click)="handleAutoSelect()"
        class="btn-secondary text-xs disabled:opacity-50"
      >
        Auto-detect from site URL
      </button>
    </div>

    @if (loading()) {
      <p class="text-sm text-[var(--color-ink-muted)]">Loading projects…</p>
    } @else if (projects().length === 0) {
      <p class="text-sm text-[var(--color-ink-muted)]">No projects found for this Jira site.</p>
    } @else {
      <div class="max-h-56 space-y-2 overflow-auto rounded-md border border-[var(--color-border)] bg-white p-3">
        @for (project of projects(); track project.key) {
          <label class="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              [checked]="selected().includes(project.key)"
              (change)="toggle(project.key, $any($event.target).checked)"
            />
            <span>
              <span class="font-medium">{{ project.key }}</span> · {{ project.name }}
            </span>
          </label>
        }
      </div>
    }

    <button
      type="button"
      [disabled]="busy() || loading()"
      (click)="handleSave()"
      class="btn-primary disabled:opacity-50"
    >
      Save project selection
    </button>
  `,
})
export class JiraProjectsPanelComponent implements OnInit {
  readonly siteUrl = input<string | null | undefined>(undefined)

  readonly onSaved = output<void>()
  readonly onError = output<string>()

  protected readonly projects = signal<JiraProject[]>([])
  protected readonly selected = signal<string[]>([])
  protected readonly busy = signal(false)
  protected readonly loading = signal(true)

  ngOnInit(): void {
    void this.loadProjects()
  }

  protected toggle(key: string, checked: boolean): void {
    this.selected.update((prev) => (checked ? [...prev, key] : prev.filter((item) => item !== key)))
  }

  private async loadProjects(): Promise<void> {
    this.loading.set(true)
    try {
      const data = await api.getProjects()
      this.projects.set(data.projects)
      this.selected.set(data.projects.filter((project) => project.selected).map((project) => project.key))
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Failed to load Jira projects')
    } finally {
      this.loading.set(false)
    }
  }

  protected async handleSave(): Promise<void> {
    this.busy.set(true)
    try {
      await api.updateProjects(this.selected())
      await api.syncIntegration('jira')
      await this.loadProjects()
      this.onSaved.emit()
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Failed to save project selection')
    } finally {
      this.busy.set(false)
    }
  }

  protected async handleAutoSelect(): Promise<void> {
    this.busy.set(true)
    try {
      await api.autoSelectJiraProject()
      await this.loadProjects()
      this.onSaved.emit()
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Could not auto-select project from site URL')
    } finally {
      this.busy.set(false)
    }
  }
}
