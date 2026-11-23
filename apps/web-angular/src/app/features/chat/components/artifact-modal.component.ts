import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core'
import { CheckCircle2, Circle, Download, FileSpreadsheet, FileText, Redo2, Trash2, Undo2, X } from 'lucide'
import { ToastService } from '../../../core/notifications/toast.service'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { Artifact } from '../../../types/artifacts'
import type { UniverAdapter } from '../../document/agent/adapters/UniverAdapter'
import { UniverContainerComponent } from '../../document/univer/univer-container.component'
import { downloadArtifact } from './artifactDownload'

/**
 * Port of React `ArtifactModal` (full-screen artifact viewer backed by Univer).
 *
 * API notes:
 * - `onUndo`, `onRedo` and `onDelete` stay function-typed inputs because React only renders the
 *   undo/redo group and the delete button when those callbacks are provided.
 * - `onUpdateContent(id, newContent)` emits `{ id, newContent }`.
 */
@Component({
  selector: 'app-artifact-modal',
  imports: [LucideIconDirective, UniverContainerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (artifact(); as artifact) {
      <div
        class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 animate-fadeIn"
      >
        <div
          class="flex flex-col h-[90vh] w-full max-w-5xl rounded-3xl bg-white shadow-2xl overflow-hidden border border-slate-200"
        >
          <!-- Modal Header -->
          <div class="flex items-center justify-between px-6 py-3.5 border-b border-slate-200 bg-white shrink-0">
            <div class="flex items-center gap-3 min-w-0">
              <div
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-[#002777] border border-blue-200"
              >
                @if (artifact.extension === 'xlsx') {
                  <svg [lucide]="icons.FileSpreadsheet" class="h-4 w-4"></svg>
                } @else {
                  <svg [lucide]="icons.FileText" class="h-4 w-4"></svg>
                }
              </div>
              <div class="min-w-0">
                <h3 class="text-sm font-bold text-slate-900 truncate" [title]="artifact.title">{{ artifact.title }}</h3>
                <p class="text-[11px] text-slate-500 uppercase font-semibold">.{{ artifact.extension }} • Vista completa</p>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <!-- Status indicator -->
              <div
                class="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border border-slate-200 bg-slate-50 text-slate-600"
              >
                @if (isDirty()) {
                  <svg [lucide]="icons.Circle" class="h-2 w-2 fill-amber-500 text-amber-500"></svg>
                  <span>Sin guardar</span>
                } @else if (isSaving()) {
                  <span>Guardando...</span>
                } @else {
                  <svg [lucide]="icons.CheckCircle2" class="h-3 w-3 text-emerald-600"></svg>
                  <span>Guardado</span>
                }
              </div>

              <!-- Undo / Redo -->
              @if (onUndo() && onRedo()) {
                <div class="flex items-center gap-0.5 bg-slate-100 rounded-xl p-0.5 border border-slate-200">
                  <button
                    type="button"
                    (click)="onUndo()?.()"
                    [disabled]="!canUndo()"
                    class="p-1.5 rounded-lg text-slate-600 hover:bg-white disabled:opacity-30 transition cursor-pointer"
                    title="Deshacer"
                  >
                    <svg [lucide]="icons.Undo2" class="h-3.5 w-3.5"></svg>
                  </button>
                  <button
                    type="button"
                    (click)="onRedo()?.()"
                    [disabled]="!canRedo()"
                    class="p-1.5 rounded-lg text-slate-600 hover:bg-white disabled:opacity-30 transition cursor-pointer"
                    title="Rehacer"
                  >
                    <svg [lucide]="icons.Redo2" class="h-3.5 w-3.5"></svg>
                  </button>
                </div>
              }

              <!-- Download -->
              <button
                type="button"
                (click)="handleDownload(artifact)"
                [disabled]="downloading()"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer shadow-2xs"
                title="Descargar documento"
              >
                <svg [lucide]="icons.Download" class="h-3.5 w-3.5"></svg>
                <span>{{ downloading() ? 'Descargando...' : 'Descargar' }}</span>
              </button>

              <!-- Delete -->
              @if (onDelete()) {
                <button
                  type="button"
                  (click)="handleDelete(artifact.id)"
                  class="p-1.5 rounded-xl text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                  title="Eliminar artefacto"
                >
                  <svg [lucide]="icons.Trash2" class="h-4 w-4"></svg>
                </button>
              }

              <!-- Close -->
              <button
                type="button"
                (click)="onClose.emit()"
                class="p-1.5 rounded-xl text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
                title="Cerrar modal"
              >
                <svg [lucide]="icons.X" class="h-4 w-4"></svg>
              </button>
            </div>
          </div>

          <!-- Modal Viewport (Univer Document Viewer) -->
          <div class="flex-1 overflow-hidden bg-slate-50 relative">
            <app-univer-container
              [adapter]="adapter()"
              [kind]="artifact.extension === 'xlsx' ? 'spreadsheet' : 'document'"
              [title]="artifact.title"
              [content]="artifact.content"
              [images]="[]"
              (onInspect)="noop()"
              (onExport)="handleDownload(artifact)"
              (onReloadFixture)="noop()"
              [hideHeader]="true"
              [mode]="'artifact'"
              (onContentChange)="onUpdateContent.emit({ id: artifact.id, newContent: $event })"
            />
          </div>
        </div>
      </div>
    }
  `,
})
export class ArtifactModalComponent {
  readonly artifact = input.required<Artifact | null>()
  readonly adapter = input.required<UniverAdapter>()
  readonly canUndo = input<boolean>(false)
  readonly canRedo = input<boolean>(false)
  readonly isDirty = input<boolean>(false)
  readonly isSaving = input<boolean>(false)
  readonly onUndo = input<(() => void) | undefined>(undefined)
  readonly onRedo = input<(() => void) | undefined>(undefined)
  readonly onDelete = input<((id: string) => void) | undefined>(undefined)

  readonly onClose = output<void>()
  readonly onUpdateContent = output<{ id: string; newContent: string }>()

  private readonly toast = inject(ToastService).toast
  protected readonly downloading = signal(false)
  protected readonly icons = { X, FileText, FileSpreadsheet, Download, Trash2, Undo2, Redo2, Circle, CheckCircle2 }

  protected noop(): void {}

  protected handleDelete(id: string): void {
    this.onDelete()?.(id)
    this.onClose.emit()
  }

  protected async handleDownload(artifact: Artifact): Promise<void> {
    this.downloading.set(true)
    try {
      const message = await downloadArtifact(artifact)
      this.toast.success(message)
    } catch {
      this.toast.error('Error al exportar el documento.')
    } finally {
      this.downloading.set(false)
    }
  }
}
