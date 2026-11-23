import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core'
import { AlertTriangle, Ban, CheckCircle2, Download, GripVertical, Loader2, Maximize2, Mic, Minus, X } from 'lucide'
import type { BackgroundJobItem } from '../../core/jobs/background-job.service'
import { LucideIconDirective } from '../icons/lucide.directive'

/** Draggable stack of background-process cards (port of React `FloatingJobToast`). */
@Component({
  selector: 'app-floating-job-toast',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (jobs().length > 0) {
      <aside
        aria-label="Notificaciones de procesos en segundo plano"
        class="fixed top-6 right-6 z-50 flex flex-col gap-3 w-80 sm:w-96 pointer-events-auto animate-fade-in font-sans"
        [style.transform]="'translate3d(' + position().x + 'px, ' + position().y + 'px, 0)'"
        (pointermove)="onPointerMove($event)"
        (pointerup)="drag = null"
        (pointercancel)="drag = null"
      >
        @for (task of jobs(); track task.id) {
          @let isComplete = task.status === 'complete';
          @let isFailed = task.status === 'failed';
          @let isCancelled = task.status === 'cancelled';
          @let inProgress = !isComplete && !isFailed && !isCancelled;
          @let isCancelling = inProgress && !!task.stageText?.toLowerCase()?.startsWith('cancelando');
          @let isCollapsed = collapsedJobs().has(task.id);
          <div
            (click)="task.onClick?.()"
            [class]="
              'bg-white border border-slate-200/90 rounded-2xl shadow-xl transition-all duration-200 ' +
              (isCollapsed ? 'px-3 py-2.5' : 'p-4') +
              ' ' +
              (task.onClick ? 'cursor-pointer hover:border-slate-300 hover:shadow-2xl' : '')
            "
          >
            <div
              class="flex items-center gap-2"
              (pointerdown)="onPointerDown($event)"
              style="cursor: grab; touch-action: none"
              title="Arrastrar notificación"
            >
              <div
                [class]="
                  'flex shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-700 shadow-2xs ' +
                  (isCollapsed ? 'h-8 w-8' : 'h-10 w-10')
                "
              >
                @if (isComplete) {
                  <svg [lucide]="icons.CheckCircle2" class="h-4 w-4 text-emerald-600"></svg>
                } @else if (isFailed) {
                  <svg [lucide]="icons.AlertTriangle" class="h-4 w-4 text-red-600"></svg>
                } @else if (isCancelled) {
                  <svg [lucide]="icons.Ban" class="h-4 w-4 text-slate-500"></svg>
                } @else if (task.type === 'download') {
                  <svg [lucide]="icons.Download" class="h-4 w-4 text-slate-700 animate-pulse"></svg>
                } @else if (task.type === 'transcription') {
                  <svg [lucide]="icons.Mic" class="h-4 w-4 text-slate-700 animate-pulse"></svg>
                } @else {
                  <svg [lucide]="icons.Loader2" class="h-4 w-4 text-slate-700 animate-spin"></svg>
                }
              </div>

              <div class="flex-1 min-w-0 space-y-1.5">
                <div class="flex items-center justify-between gap-2">
                  <h4 class="text-xs font-bold text-slate-900 truncate" [title]="task.title">{{ task.title }}</h4>

                  <div class="flex items-center gap-1 shrink-0">
                    @if (inProgress && (task.onCancel || hasCancelHandler())) {
                      <button
                        type="button"
                        [disabled]="isCancelling"
                        (click)="cancel($event, task, isCancelling)"
                        [class]="
                          'text-[11px] font-semibold transition shrink-0 ' +
                          (isCancelling
                            ? 'text-slate-400 cursor-not-allowed animate-pulse'
                            : 'text-slate-400 hover:text-red-600 cursor-pointer')
                        "
                        [title]="isCancelling ? 'Cancelando proceso...' : 'Cancelar proceso'"
                      >
                        {{ isCancelling ? 'Cancelando...' : 'Cancelar' }}
                      </button>
                    }
                    @if (!inProgress && (task.onDismiss || hasDismissHandler())) {
                      <button
                        type="button"
                        (click)="dismiss($event, task)"
                        class="text-slate-400 hover:text-slate-600 p-0.5 rounded transition shrink-0 cursor-pointer"
                        title="Cerrar notificación"
                      >
                        <svg [lucide]="icons.X" class="h-3.5 w-3.5"></svg>
                      </button>
                    }
                    <button
                      type="button"
                      (click)="toggleCollapsed($event, task.id)"
                      class="text-slate-400 hover:text-slate-700 p-0.5 rounded transition cursor-pointer"
                      [title]="isCollapsed ? 'Expandir proceso' : 'Minimizar proceso'"
                      [attr.aria-label]="isCollapsed ? 'Expandir proceso' : 'Minimizar proceso'"
                    >
                      @if (isCollapsed) {
                        <svg [lucide]="icons.Maximize2" class="h-3.5 w-3.5"></svg>
                      } @else {
                        <svg [lucide]="icons.Minus" class="h-3.5 w-3.5"></svg>
                      }
                    </button>
                  </div>
                </div>

                @if (!isCollapsed) {
                  <div class="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden border border-slate-200/60">
                    <div
                      [class]="
                        'h-full transition-all duration-300 rounded-full ' +
                        (isComplete
                          ? 'bg-emerald-600'
                          : isFailed
                            ? 'bg-red-600'
                            : isCancelled || isCancelling
                              ? 'bg-slate-400'
                              : 'bg-[#002777]')
                      "
                      [style.width]="isCancelled ? '0%' : clampProgress(task.progress) + '%'"
                    ></div>
                  </div>

                  <div class="flex items-center justify-between text-[11px] text-slate-500 font-medium">
                    <span class="truncate max-w-[210px]" [title]="task.stageText || task.speedOrSize || ''">
                      {{ task.stageText || task.speedOrSize || task.progress + '%' }}
                    </span>
                    <div class="flex items-center gap-2 shrink-0">
                      @if (task.eta && inProgress && !isCancelling) {
                        <span class="text-slate-400 font-mono text-[10px]">{{ task.eta }}</span>
                      }
                      @if (!isCancelled && !isCancelling) {
                        <span class="font-bold font-mono text-slate-800">{{ task.progress }}%</span>
                      }
                    </div>
                  </div>
                }
              </div>
              <svg [lucide]="icons.GripVertical" class="h-4 w-4 shrink-0 text-slate-300" aria-hidden="true"></svg>
            </div>
          </div>
        }
      </aside>
    }
  `,
})
export class FloatingJobToastComponent {
  readonly jobs = input<BackgroundJobItem[]>([])
  /** Set to true when the parent listens to `onCancelJob` (React checked `onCancelJob` prop presence). */
  readonly hasCancelHandler = input(false)
  /** Set to true when the parent listens to `onDismissJob`. */
  readonly hasDismissHandler = input(false)
  readonly onCancelJob = output<string>()
  readonly onDismissJob = output<string>()

  protected readonly icons = { AlertTriangle, Ban, CheckCircle2, Download, GripVertical, Loader2, Maximize2, Mic, Minus, X }
  protected readonly collapsedJobs = signal<Set<string>>(new Set())
  protected readonly position = signal({ x: 0, y: 0 })
  protected drag: { startX: number; startY: number; originX: number; originY: number } | null = null

  protected clampProgress(progress: number): number {
    return Math.min(100, Math.max(4, progress))
  }

  protected onPointerMove(event: PointerEvent): void {
    if (!this.drag) return
    this.position.set({
      x: this.drag.originX + event.clientX - this.drag.startX,
      y: this.drag.originY + event.clientY - this.drag.startY,
    })
  }

  protected onPointerDown(event: PointerEvent): void {
    if ((event.target as HTMLElement).closest('button')) return
    const pos = this.position()
    this.drag = { startX: event.clientX, startY: event.clientY, originX: pos.x, originY: pos.y }
    ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
  }

  protected toggleCollapsed(event: MouseEvent, id: string): void {
    event.stopPropagation()
    this.collapsedJobs.update((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  protected cancel(event: MouseEvent, task: BackgroundJobItem, isCancelling: boolean): void {
    event.stopPropagation()
    if (isCancelling) return
    if (task.onCancel) task.onCancel()
    else this.onCancelJob.emit(task.id)
  }

  protected dismiss(event: MouseEvent, task: BackgroundJobItem): void {
    event.stopPropagation()
    if (task.onDismiss) task.onDismiss()
    else this.onDismissJob.emit(task.id)
  }
}
