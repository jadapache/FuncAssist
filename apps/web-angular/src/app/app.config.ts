import {
  ApplicationConfig,
  ErrorHandler,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
} from '@angular/core'
import { provideRouter, withComponentInputBinding, withInMemoryScrolling } from '@angular/router'
import { routes } from './app.routes'
import { GlobalErrorHandler } from './core/errors/global-error-handler'

export const appConfig: ApplicationConfig = {
  providers: [
    // Zone-based change detection keeps async/await, fetch streaming and Worker callbacks rendering
    // without manual triggers, which matches how the React hooks behaved.
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding(), withInMemoryScrolling({ scrollPositionRestoration: 'top' })),
    provideBrowserGlobalErrorListeners(),
    { provide: ErrorHandler, useClass: GlobalErrorHandler },
  ],
}
