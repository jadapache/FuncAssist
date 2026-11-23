import { Injectable, signal } from '@angular/core'
import { DEFAULT_DISPLAY_NAME } from '../../constants/app'

/**
 * Replaces the React `<Outlet context={{ displayName, setDisplayName }} />` that AppLayout
 * shared with its child pages (Dashboard reads it, Profile updates it).
 */
@Injectable({ providedIn: 'root' })
export class LayoutContextService {
  readonly displayName = signal<string>(DEFAULT_DISPLAY_NAME)
  readonly appVersion = signal<string | null>(null)

  setDisplayName(name: string): void {
    this.displayName.set(name)
  }
}
