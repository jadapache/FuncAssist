import { ErrorHandler, Injectable, NgZone, inject, signal } from '@angular/core'

/** Holds the error shown by the global error screen (React `ErrorBoundary` fallback). */
@Injectable({ providedIn: 'root' })
export class ErrorBoundaryState {
  readonly error = signal<Error | null>(null)

  reset(): void {
    this.error.set(null)
  }
}

/**
 * Global Angular ErrorHandler (replaces React `ErrorBoundary`).
 *
 * React's boundary only caught render errors; async failures were handled locally by each feature.
 * To keep that behaviour, unhandled promise rejections are logged but do NOT replace the UI —
 * only synchronous errors (templates, lifecycle hooks, event handlers) show the fallback screen.
 */
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private readonly state = inject(ErrorBoundaryState)
  private readonly zone = inject(NgZone)

  handleError(error: unknown): void {
    console.error('Error caught by ErrorBoundary:', error)
    const rejection = (error as { rejection?: unknown } | null)?.rejection
    const isUnhandledRejection =
      rejection !== undefined || (error instanceof Error && error.message.startsWith('Uncaught (in promise)'))
    if (isUnhandledRejection) return

    const normalized = error instanceof Error ? error : new Error(String(error))
    this.zone.run(() => this.state.error.set(normalized))
  }
}
