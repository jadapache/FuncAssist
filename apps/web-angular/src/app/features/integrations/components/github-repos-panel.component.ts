import { ChangeDetectionStrategy, Component, OnInit, output, signal } from '@angular/core'
import { api } from '../../../api/client'

type Repo = {
  full_name: string
  name: string
  private: boolean
  selected: boolean
  html_url: string
}

/** Port of React `GitHubReposPanel`. */
@Component({
  selector: 'app-github-repos-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="mt-5 space-y-4 border-t border-[var(--color-line)] pt-5">
      <h3 class="text-sm font-semibold">Repositorios</h3>
      <p class="text-xs text-[var(--color-ink-muted)]">
        Solo los repositorios seleccionados son accesibles para las funcionalidades. Nada se selecciona automáticamente.
      </p>
      <div class="max-h-56 space-y-2 overflow-auto rounded-md border border-[var(--color-line)] bg-white p-3">
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
      <button type="button" [disabled]="busy()" (click)="handleSave()" class="btn-primary disabled:opacity-50">
        Guardar selección
      </button>
      @if (prs().length) {
        <div>
          <h4 class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-muted)]">
            PRs en vivo (muestra)
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
export class GitHubReposPanelComponent implements OnInit {
  readonly onSaved = output<void>()
  readonly onError = output<string>()

  protected readonly repos = signal<Repo[]>([])
  protected readonly selected = signal<string[]>([])
  protected readonly busy = signal(false)
  protected readonly prs = signal<Array<Record<string, unknown>>>([])

  protected readonly str = String

  ngOnInit(): void {
    const load = async () => {
      const data = await api.getRepositories()
      this.repos.set(data.repositories)
      this.selected.set(data.repositories.filter((repo) => repo.selected).map((repo) => repo.full_name))
    }
    void load().catch((err) => this.onError.emit(err instanceof Error ? err.message : 'Failed to load repos'))
  }

  protected prKey(pr: Record<string, unknown>): string {
    return `${pr['repo']}-${pr['number']}`
  }

  protected toggle(fullName: string, checked: boolean): void {
    this.selected.update((prev) => (checked ? [...prev, fullName] : prev.filter((item) => item !== fullName)))
  }

  protected async handleSave(): Promise<void> {
    const selected = this.selected()
    this.busy.set(true)
    try {
      await api.updateRepositories('github', selected)
      this.onSaved.emit()
      if (selected.length) {
        const prData = await api.getPullRequests()
        this.prs.set(prData.pull_requests.slice(0, 8))
      } else {
        this.prs.set([])
      }
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Failed to save repos')
    } finally {
      this.busy.set(false)
    }
  }
}
