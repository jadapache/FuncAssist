import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core'
import { RouterOutlet } from '@angular/router'
import { AlertTriangle } from 'lucide'
import { AuthService } from './core/auth/auth.service'
import { ErrorBoundaryState } from './core/errors/global-error-handler'
import { BackgroundJobService } from './core/jobs/background-job.service'
import { LoadingService } from './core/loading/loading.service'
import { ChatStore } from './features/chat/state/chat.store'
import { TranscriptionStore } from './features/transcription/context/transcription.store'
import { FloatingJobToastComponent } from './shared/components/floating-job-toast.component'
import { ToastContainerComponent } from './shared/components/toast-container.component'
import { LucideIconDirective } from './shared/icons/lucide.directive'

/**
 * Root component — Angular equivalent of React `App.tsx`.
 * The React provider tree (Auth, User, Toast, Sidebar, Loading, BackgroundJobs, Transcription, Chat)
 * maps to root services; the global ones that do work at startup are injected here so they start
 * eagerly, exactly like the React providers mounted at boot.
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ToastContainerComponent, FloatingJobToastComponent, LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (errorState.error(); as error) {
      <div class="min-h-screen flex items-center justify-center bg-slate-100 p-6">
        <div
          class="max-w-md w-full bg-white rounded-2xl shadow-xl border border-slate-200 p-8 space-y-4 animate-fade-in"
        >
          <div class="flex items-center gap-3">
            <div class="p-2.5 rounded-xl bg-red-100 text-red-600">
              <svg [lucide]="icons.AlertTriangle" class="h-6 w-6"></svg>
            </div>
            <div>
              <h2 class="text-base font-bold text-slate-900">Ha ocurrido un error inesperado</h2>
              <p class="text-xs text-slate-500">Se detectó una excepción en la interfaz</p>
            </div>
          </div>
          <p class="text-xs text-slate-600 leading-relaxed">
            La vista actual encontró un problema durante su ejecución. Puedes intentar restablecer el estado o recargar
            la página.
          </p>
          <details class="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-xl p-3">
            <summary class="cursor-pointer font-semibold text-slate-700">Detalles técnicos</summary>
            <pre class="mt-2 text-[11px] overflow-auto whitespace-pre-wrap font-mono text-red-700">{{
              error.message
            }}</pre>
          </details>
          <div class="flex gap-3 pt-2">
            <button
              type="button"
              (click)="errorState.reset()"
              class="flex-1 px-4 py-2 bg-[#002777] hover:bg-[#001e5c] text-white rounded-xl text-xs font-bold transition shadow-xs cursor-pointer"
            >
              Reintentar
            </button>
            <button
              type="button"
              (click)="reload()"
              class="flex-1 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition border border-slate-200 cursor-pointer"
            >
              Recargar página
            </button>
          </div>
        </div>
      </div>
    } @else {
      <!-- Top progress bar with brand gradient (React LoadingProvider) -->
      <div
        [class]="
          'fixed top-0 left-0 right-0 z-50 pointer-events-none transition-opacity duration-300 ' +
          (loading.isLoading() ? 'opacity-100' : 'opacity-0')
        "
        aria-hidden="true"
      >
        <div class="h-0.5 w-full bg-gradient-to-r from-[#002777] via-[#004497] to-cyan-400 animate-shimmer"></div>
      </div>

      <app-toast-container />
      <app-floating-job-toast
        [jobs]="jobs.jobs()"
        [hasCancelHandler]="true"
        [hasDismissHandler]="true"
        (onCancelJob)="cancelJob($event)"
        (onDismissJob)="jobs.removeJob($event)"
      />

      @if (showSessionCheck()) {
        <!-- React <ProtectedRoute /> loading state while the stored token is validated -->
        <div class="flex items-center justify-center min-h-screen bg-slate-50">
          <div class="text-center">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-[#002777] mx-auto mb-4"></div>
            <p class="text-slate-600 font-medium text-xs">Verificando sesión...</p>
          </div>
        </div>
      }
      <router-outlet />
    }
  `,
})
export class App {
  protected readonly errorState = inject(ErrorBoundaryState)
  protected readonly loading = inject(LoadingService)
  protected readonly jobs = inject(BackgroundJobService)
  private readonly auth = inject(AuthService)
  protected readonly icons = { AlertTriangle }

  constructor() {
    // Eagerly start global stores (React mounted these providers at boot).
    inject(ChatStore)
    inject(TranscriptionStore)
  }

  protected readonly showSessionCheck = computed(
    () => this.auth.isLoading() && !window.location.pathname.startsWith('/login'),
  )

  protected cancelJob(id: string): void {
    void this.jobs.cancelJob(id)
  }

  protected reload(): void {
    window.location.reload()
  }
}
