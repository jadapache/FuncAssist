import { ChangeDetectionStrategy, Component, effect, input, output, signal, untracked } from '@angular/core'
import { api } from '../../../api/client'

type Repo = {
  full_name: string
  name: string
  private: boolean
  selected: boolean
  html_url: string
}

/** Port of React `GitHostingReposPanel`. */
@Component({
  selector: 'app-git-hosting-repos-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="mt-5 space-y-4 border-t border-[var(--color-border)] pt-5">
      <h3 class="text-sm font-semibold">{{ heading() }}</h3>
      <p class="text-xs text-[var(--color-ink-muted)]">{{ description() }}</p>

      @if (loading()) {
        <p class="text-sm text-[var(--color-ink-muted)]">Cargando repositorios...</p>
      } @else if (repos().length === 0) {
        <p class="text-sm text-[var(--color-ink-muted)]">
          No se encontraron repositorios. Comprueba que tu token o aplicación OAuth tenga acceso a los repositorios de esta cuenta.
        </p>
      } @else {
        <div class="max-h-56 space-y-2 overflow-auto rounded-md border border-[var(--color-border)] bg-white p-3">
          @for (repo of repos(); track repo.full_name) {
            <label class="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                [checked]="selected().includes(repo.full_name)"
                (change)="toggle(repo.full_name, $any($event.target).checked)"
              />
              <span>{{ repo.full_name }}</span>
              @if (repo.private) {
                <span class="text-xs text-[var(--color-ink-muted)]">private</span>
              }
            </label>
          }
        </div>
      }

      <button
        type="button"
        [disabled]="busy() || loading() || repos().length === 0"
        (click)="handleSave()"
        class="btn-primary disabled:opacity-50"
      >
        Guardar selección
      </button>

      @if (prs().length) {
        <div>
          <h4 class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-muted)]">
            Live {{ prLabel() }} (sample)
          </h4>
          <ul class="mt-2 space-y-1 text-sm">
            @for (pr of prs(); track prKey(pr)) {
              <li>#{{ str(pr['number']) }} {{ str(pr['title']) }} · {{ str(pr['repo']) }}</li>
            }
          </ul>
        </div>
      }
    </div>
  `,
})
export class GitHostingReposPanelComponent {
  readonly integrationId = input.required<'github' | 'gitlab'>()
  readonly heading = input.required<string>()
  readonly description = input.required<string>()

  readonly onSaved = output<void>()
  readonly onError = output<string>()

  protected readonly repos = signal<Repo[]>([])
  protected readonly selected = signal<string[]>([])
  protected readonly busy = signal(false)
  protected readonly loading = signal(true)
  protected readonly prs = signal<Array<Record<string, unknown>>>([])

  protected readonly str = String

  constructor() {
    // useEffect(() => { loadRepos() }, [integrationId])
    effect(() => {
      const id = this.integrationId()
      untracked(() => void this.loadRepos(id))
    })
  }

  protected prKey(pr: Record<string, unknown>): string {
    return `${pr['repo']}-${pr['number']}`
  }

  protected prLabel(): string {
    return this.integrationId() === 'gitlab' ? 'MRs' : 'PRs'
  }

  protected toggle(fullName: string, checked: boolean): void {
    this.selected.update((prev) => (checked ? [...prev, fullName] : prev.filter((item) => item !== fullName)))
  }

  private async loadRepos(integrationId: 'github' | 'gitlab'): Promise<void> {
    this.loading.set(true)
    try {
      const data = await api.getRepositories(integrationId)
      this.repos.set(data.repositories)
      this.selected.set(data.repositories.filter((repo) => repo.selected).map((repo) => repo.full_name))
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Failed to load repositories')
    } finally {
      this.loading.set(false)
    }
  }

  protected async handleSave(): Promise<void> {
    const integrationId = this.integrationId()
    const selected = this.selected()
    this.busy.set(true)
    try {
      await api.updateRepositories(integrationId, selected)
      if (selected.length) {
        await api.syncIntegration(integrationId)
        const prData = await api.getPullRequests(integrationId)
        this.prs.set(prData.pull_requests.slice(0, 8))
      } else {
        this.prs.set([])
      }
      this.onSaved.emit()
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Failed to save selection')
    } finally {
      this.busy.set(false)
    }
  }
}
