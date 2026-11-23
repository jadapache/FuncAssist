import { Injectable, signal } from '@angular/core'

/** Angular port of React `SidebarContext`. */
@Injectable({ providedIn: 'root' })
export class SidebarService {
  readonly isCollapsed = signal(false)

  setIsCollapsed(collapsed: boolean): void {
    this.isCollapsed.set(collapsed)
  }

  toggleSidebar(): void {
    this.isCollapsed.update((prev) => !prev)
  }
}
