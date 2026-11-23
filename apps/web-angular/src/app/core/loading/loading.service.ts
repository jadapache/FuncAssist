import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core'
import { NavigationEnd, Router } from '@angular/router'
import { filter } from 'rxjs'

/**
 * Angular port of React `LoadingContext`: drives the thin brand progress bar at the top of the page.
 * Pulses for 280 ms on every navigation (path or query change), plus explicit start/stop/withLoading.
 */
@Injectable({ providedIn: 'root' })
export class LoadingService {
  private readonly activeRequests = signal(0)
  readonly isLoading = computed(() => this.activeRequests() > 0)

  constructor() {
    const router = inject(Router)
    const sub = router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      this.startLoading()
      setTimeout(() => this.stopLoading(), 280)
    })
    inject(DestroyRef).onDestroy(() => sub.unsubscribe())
  }

  startLoading(): void {
    this.activeRequests.update((prev) => prev + 1)
  }

  stopLoading(): void {
    this.activeRequests.update((prev) => Math.max(0, prev - 1))
  }

  async withLoading<T>(action: () => Promise<T>): Promise<T> {
    this.startLoading()
    try {
      return await action()
    } finally {
      this.stopLoading()
    }
  }
}
