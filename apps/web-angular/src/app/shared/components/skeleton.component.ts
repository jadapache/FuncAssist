import { ChangeDetectionStrategy, Component, input } from '@angular/core'

/**
 * Base Skeleton element with modern shimmer animation (port of React `Skeleton`).
 * The host element IS the skeleton box (React rendered a bare <div>), so parent utilities such as
 * `space-y-*` keep applying to it. Its default `display:block` lives in the global base layer.
 */
@Component({
  selector: "app-skeleton",
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    "[class]": "'animate-shimmer rounded-lg bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 ' + className()",
    style: "background-size: 200% 100%; animation: shimmer 1.8s infinite linear",
    "aria-hidden": "true",
  },
  template: "",
})
export class SkeletonComponent {
  readonly className = input("")
}

/** Skeleton for the Integrations tab (Jira, GitHub, GitLab). */
@Component({
  selector: 'app-integrations-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="space-y-6">
      <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div class="flex items-center justify-between">
          <div class="space-y-2">
            <app-skeleton className="h-5 w-44" />
            <app-skeleton className="h-3.5 w-80" />
          </div>
          <app-skeleton className="h-8 w-24 rounded-lg" />
        </div>
        <div class="grid gap-3 sm:grid-cols-2 pt-2">
          <app-skeleton className="h-10 w-full rounded-lg" />
          <app-skeleton className="h-10 w-full rounded-lg" />
        </div>
      </div>
      @for (idx of [1, 2, 3]; track idx) {
        <div class="card p-6 space-y-5">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="space-y-2">
              <div class="flex items-center gap-3">
                <app-skeleton className="h-8 w-8 rounded-lg" />
                <app-skeleton className="h-6 w-36" />
              </div>
              <app-skeleton className="h-4 w-72" />
            </div>
            <app-skeleton className="h-6 w-24 rounded-full" />
          </div>
          <div class="space-y-2 pt-2 border-t border-slate-100">
            <app-skeleton className="h-3.5 w-56" />
            <app-skeleton className="h-3.5 w-48" />
          </div>
          <div class="flex gap-3 pt-2">
            <app-skeleton className="h-9 w-32 rounded-lg" />
            <app-skeleton className="h-9 w-28 rounded-lg" />
          </div>
        </div>
      }
    </div>
  `,
})
export class IntegrationsSkeletonComponent {}

/** Skeleton for AI Models tab. */
@Component({
  selector: 'app-ai-models-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="space-y-6">
      <div class="card p-6 space-y-4">
        <div class="flex items-center justify-between">
          <div class="space-y-2">
            <app-skeleton className="h-6 w-52" />
            <app-skeleton className="h-3.5 w-96" />
          </div>
          <app-skeleton className="h-9 w-36 rounded-xl" />
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5 pt-2">
          @for (p of [1, 2, 3, 4, 5, 6]; track p) {
            <app-skeleton className="h-16 w-full rounded-xl" />
          }
        </div>
      </div>
      <div class="card p-6 space-y-5">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <app-skeleton className="h-9 w-9 rounded-xl" />
            <div class="space-y-1.5">
              <app-skeleton className="h-5 w-48" />
              <app-skeleton className="h-3.5 w-72" />
            </div>
          </div>
          <app-skeleton className="h-6 w-6 rounded-md" />
        </div>
        <div class="space-y-4 pt-2">
          <app-skeleton className="h-10 w-full rounded-lg" />
          <div class="grid gap-3 sm:grid-cols-2">
            <app-skeleton className="h-24 w-full rounded-xl" />
            <app-skeleton className="h-24 w-full rounded-xl" />
          </div>
        </div>
      </div>
    </div>
  `,
})
export class AiModelsSkeletonComponent {}

/** Skeleton for User Approvals tab. */
@Component({
  selector: 'app-user-approvals-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="card p-6 md:p-8 space-y-6">
      <div class="flex items-center justify-between border-b border-slate-100 pb-4">
        <div class="flex items-center gap-3">
          <app-skeleton className="h-7 w-7 rounded-lg" />
          <div class="space-y-1.5">
            <app-skeleton className="h-5 w-60" />
            <app-skeleton className="h-3.5 w-80" />
          </div>
        </div>
        <app-skeleton className="h-8 w-24 rounded-lg" />
      </div>
      <div class="space-y-3">
        @for (u of [1, 2, 3]; track u) {
          <div
            class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-100 bg-white p-4 shadow-sm"
          >
            <div class="space-y-2">
              <div class="flex items-center gap-2">
                <app-skeleton className="h-4 w-28" />
                <app-skeleton className="h-4 w-20 rounded-full" />
              </div>
              <app-skeleton className="h-3 w-48" />
              <app-skeleton className="h-2.5 w-32" />
            </div>
            <div class="flex items-center gap-2">
              <app-skeleton className="h-8 w-28 rounded-lg" />
              <app-skeleton className="h-8 w-24 rounded-lg" />
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class UserApprovalsSkeletonComponent {}

/** Skeleton for Dashboard Overview widgets. */
@Component({
  selector: 'app-dashboard-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="space-y-8">
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        @for (i of [1, 2, 3, 4]; track i) {
          <div class="card p-5 space-y-3">
            <div class="flex items-center justify-between">
              <app-skeleton className="h-4 w-24" />
              <app-skeleton className="h-8 w-8 rounded-lg" />
            </div>
            <app-skeleton className="h-7 w-20" />
            <app-skeleton className="h-3.5 w-36" />
          </div>
        }
      </div>
      <div class="grid gap-6 xl:grid-cols-5">
        <div class="space-y-4 xl:col-span-2">
          <app-skeleton className="h-6 w-40" />
          <div class="space-y-3">
            @for (t of [1, 2, 3]; track t) {
              <app-skeleton className="h-24 w-full rounded-2xl" />
            }
          </div>
        </div>
        <div class="space-y-4 xl:col-span-3">
          <app-skeleton className="h-6 w-40" />
          <app-skeleton className="h-64 w-full rounded-2xl" />
        </div>
      </div>
    </div>
  `,
})
export class DashboardSkeletonComponent {}

/** Skeleton for Chat view. */
@Component({
  selector: 'app-chat-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="flex flex-col h-full w-full p-4 md:p-6 space-y-6">
      <div class="flex items-center justify-between border-b border-slate-100 pb-4">
        <div class="space-y-2">
          <app-skeleton className="h-6 w-48" />
          <app-skeleton className="h-3.5 w-72" />
        </div>
        <app-skeleton className="h-9 w-28 rounded-xl" />
      </div>
      <div class="flex-1 space-y-4 py-4">
        <div class="flex items-start gap-3 max-w-xl">
          <app-skeleton className="h-8 w-8 rounded-full shrink-0" />
          <app-skeleton className="h-16 w-full rounded-2xl" />
        </div>
        <div class="flex items-start justify-end gap-3 max-w-xl ml-auto">
          <app-skeleton className="h-14 w-full rounded-2xl" />
          <app-skeleton className="h-8 w-8 rounded-full shrink-0" />
        </div>
        <div class="flex items-start gap-3 max-w-2xl">
          <app-skeleton className="h-8 w-8 rounded-full shrink-0" />
          <app-skeleton className="h-28 w-full rounded-2xl" />
        </div>
      </div>
      <div class="pt-2">
        <app-skeleton className="h-14 w-full rounded-2xl" />
      </div>
    </div>
  `,
})
export class ChatSkeletonComponent {}

/** Skeleton for Knowledge Page document catalog. */
@Component({
  selector: 'app-knowledge-docs-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      @for (i of [1, 2, 3, 4, 5, 6]; track i) {
        <div class="card p-5 space-y-4">
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <app-skeleton className="h-10 w-10 rounded-xl" />
              <div class="space-y-1.5">
                <app-skeleton className="h-4 w-32" />
                <app-skeleton className="h-3 w-20" />
              </div>
            </div>
            <app-skeleton className="h-6 w-16 rounded-full" />
          </div>
          <app-skeleton className="h-3 w-full" />
          <div class="flex items-center justify-between pt-2 border-t border-slate-100">
            <app-skeleton className="h-3 w-24" />
            <app-skeleton className="h-7 w-16 rounded-lg" />
          </div>
        </div>
      }
    </div>
  `,
})
export class KnowledgeDocsSkeletonComponent {}

/** Skeleton for Transcripciones list. */
@Component({
  selector: 'app-transcriptions-skeleton',
  imports: [SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="space-y-3">
      @for (i of [1, 2, 3, 4]; track i) {
        <div class="card p-4 flex items-center justify-between gap-4">
          <div class="flex items-center gap-3.5 min-w-0 flex-1">
            <app-skeleton className="h-10 w-10 rounded-xl shrink-0" />
            <div class="space-y-1.5 min-w-0 flex-1">
              <app-skeleton className="h-4 w-44" />
              <app-skeleton className="h-3 w-64" />
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <app-skeleton className="h-8 w-24 rounded-lg" />
            <app-skeleton className="h-8 w-8 rounded-lg" />
          </div>
        </div>
      }
    </div>
  `,
})
export class TranscriptionsSkeletonComponent {}
