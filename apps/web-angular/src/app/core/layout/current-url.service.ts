import { Injectable, computed, inject, signal } from '@angular/core'
import { NavigationEnd, Router } from '@angular/router'
import { filter } from 'rxjs'

/**
 * Current URL as signals — replaces React Router's `useLocation()` / `useSearchParams()` reads.
 * `pathname` excludes query string and fragment, like `location.pathname`.
 */
@Injectable({ providedIn: 'root' })
export class CurrentUrlService {
  private readonly router = inject(Router)
  readonly url = signal<string>(this.router.url)

  readonly pathname = computed(() => {
    const raw = this.url().split(/[?#]/)[0] || '/'
    return raw.length > 1 && raw.endsWith('/') ? raw.slice(0, -1) : raw
  })
  readonly searchParams = computed(() => new URLSearchParams(this.url().split('?')[1]?.split('#')[0] ?? ''))

  constructor() {
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe((e) => {
      this.url.set((e as NavigationEnd).urlAfterRedirects)
    })
  }

  /** React Router `NavLink` matching: exact (`end`) or segment-prefix match. */
  isActive(to: string, end = false): boolean {
    const path = this.pathname()
    if (end || to === '/') return path === to
    return path === to || path.startsWith(to + '/')
  }
}
