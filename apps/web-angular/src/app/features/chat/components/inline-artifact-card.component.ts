import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core'
import { Download, ExternalLink, FileText } from 'lucide'
import { ToastService } from '../../../core/notifications/toast.service'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { Artifact } from '../../../types/artifacts'
import { downloadArtifact, formatApproxSize } from './artifactDownload'

/** Port of React `InlineArtifactCard`. */
@Component({
  selector: 'app-inline-artifact-card',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div
      class="my-2.5 flex items-center justify-between gap-3 rounded-2xl border border-blue-100 bg-blue-50/60 p-3.5 shadow-2xs transition-all hover:bg-blue-50/90"
    >
      <div class="flex items-center gap-3 min-w-0">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
          <svg [lucide]="icons.FileText" class="h-5 w-5"></svg>
        </div>
        <div class="min-w-0 flex-1">
          <h4 class="text-xs font-bold text-slate-900 truncate" [title]="artifact().title">{{ artifact().title }}</h4>
          <p class="text-[11px] text-slate-500 truncate mt-0.5">{{ artifact().extension === 'xlsx' ? 'Hoja de Cálculo' : 'Documento' }} • {{ approxSize() }}</p>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <button
          type="button"
          (click)="handleDownload()"
          class="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-slate-900 transition cursor-pointer"
          title="Descargar documento"
        >
          <svg [lucide]="icons.Download" class="h-3.5 w-3.5 text-slate-500"></svg>
          <span>Descargar</span>
        </button>

        <button
          type="button"
          (click)="onOpen.emit(artifact())"
          class="inline-flex items-center gap-1.5 rounded-xl bg-[#001744] px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-[#002777] transition cursor-pointer"
          title="Abrir documento en vista detallada"
        >
          <svg [lucide]="icons.ExternalLink" class="h-3.5 w-3.5"></svg>
          <span>Abrir</span>
        </button>
      </div>
    </div>
  `,
})
export class InlineArtifactCardComponent {
  readonly artifact = input.required<Artifact>()
  readonly onOpen = output<Artifact>()

  private readonly toast = inject(ToastService).toast
  protected readonly icons = { FileText, Download, ExternalLink }

  // Estimar tamaño aproximado basado en caracteres
  protected readonly approxSize = computed(() => formatApproxSize(this.artifact().content))

  protected async handleDownload(): Promise<void> {
    try {
      const message = await downloadArtifact(this.artifact())
      this.toast.success(message)
    } catch {
      this.toast.error('Error al exportar el documento.')
    }
  }
}
