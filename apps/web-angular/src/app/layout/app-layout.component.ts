import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core'
import { RouterOutlet } from '@angular/router'
import { api } from '../api/client'
import { LayoutContextService } from '../core/layout/layout-context.service'
import { AppSidebarComponent } from './app-sidebar.component'

/** Authenticated application shell (port of React `AppLayout`). */
@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, AppSidebarComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="relative flex h-screen w-screen overflow-hidden bg-white text-slate-900">
      <!-- Ambient background -->
      <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-white" aria-hidden="true">
        <div class="absolute -left-32 top-0 h-96 w-96 rounded-full bg-blue-100/60 blur-3xl animate-float"></div>
        <div
          class="absolute -right-32 top-1/4 h-80 w-80 rounded-full bg-cyan-100/50 blur-3xl animate-float-delayed"
        ></div>
        <div class="absolute bottom-0 left-1/3 h-64 w-64 rounded-full bg-sky-50/80 blur-3xl"></div>
        <div
          class="absolute inset-0 opacity-[0.35]"
          style="background-image: radial-gradient(circle at 1px 1px, rgb(229 231 235) 1px, transparent 0); background-size: 32px 32px"
        ></div>
      </div>

      <!-- Main Collapsible App Sidebar -->
      <app-sidebar [displayName]="layout.displayName()" [version]="layout.appVersion()" />

      <!-- Main Application Area -->
      <main class="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        <div class="flex-1 h-full min-w-0 overflow-y-auto">
          <router-outlet />
        </div>
      </main>
    </div>
  `,
})
export class AppLayoutComponent implements OnInit {
  protected readonly layout = inject(LayoutContextService)

  async ngOnInit(): Promise<void> {
    try {
      const settings = await api.getSettings()
      if (settings.display_name) this.layout.setDisplayName(settings.display_name)
      if (settings.version) this.layout.appVersion.set(settings.version)
    } catch {
      // optional on first boot
    }
  }
}
