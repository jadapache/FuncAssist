import { ChangeDetectionStrategy, Component, OnInit, output, signal } from '@angular/core'
import { api } from '../../../api/client'

/** Port of React `JiraIssuesPreview`. Renders nothing until issues are loaded (React returned null). */
@Component({
  selector: 'app-jira-issues-preview',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (issues().length) {
      <div class="mt-5 border-t border-[var(--color-line)] pt-5">
        <h3 class="text-sm font-semibold">Live issues (sample)</h3>
        <ul class="mt-2 space-y-1 text-sm">
          @for (issue of issues(); track str(issue['key'])) {
            <li>
              <span class="font-medium">{{ str(issue['key']) }}</span> {{ str(issue['summary']) }} ·
              <span class="text-[var(--color-ink-muted)]">{{ str(issue['status']) }}</span>
            </li>
          }
        </ul>
      </div>
    }
  `,
})
export class JiraIssuesPreviewComponent implements OnInit {
  readonly onError = output<string>()

  protected readonly issues = signal<Array<Record<string, unknown>>>([])
  protected readonly str = String

  ngOnInit(): void {
    void api
      .getIssues()
      .then((data) => this.issues.set(data.issues.slice(0, 10)))
      .catch((err) => this.onError.emit(err instanceof Error ? err.message : 'Failed to load issues'))
  }
}
