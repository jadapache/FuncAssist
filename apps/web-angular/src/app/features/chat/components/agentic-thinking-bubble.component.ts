import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core'
import { CheckCircle2, ChevronDown, ChevronUp, Database, Loader2, Square, XCircle } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { AgentRunSource, AgentRunStep } from '../types/agentEvents'

/**
 * Port of React `AgenticThinkingBubble`.
 * `onCancel` stays a function-typed input (not an output) because the React component only renders
 * the "Cancelar" button when the callback is provided.
 */
@Component({
  selector: 'app-agentic-thinking-bubble',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (isVisible()) {
      <div
        class="flex flex-col gap-2 p-2.5 rounded-xl bg-slate-100/90 border border-slate-200/80 text-slate-800 text-xs my-2 animate-in fade-in duration-150 max-w-xl"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            @if (isCancelled()) {
              <svg [lucide]="icons.XCircle" class="h-4 w-4 text-rose-600"></svg>
            } @else if (isProcessing()) {
              <svg [lucide]="icons.Loader2" class="h-4 w-4 animate-spin text-[#002777]"></svg>
            } @else {
              <svg [lucide]="icons.CheckCircle2" class="h-4 w-4 text-emerald-600"></svg>
            }
            <span class="font-semibold tracking-wide">{{ status() }}</span>
          </div>
          <div class="flex items-center gap-1.5">
            @if (hasTimeline()) {
              <button
                type="button"
                (click)="isExpanded.set(!isExpanded())"
                [attr.aria-label]="isExpanded() ? 'Ocultar detalles' : 'Ver etapas'"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
              >
                <span>{{ steps().length }} etapas</span>
                @if (isExpanded()) {
                  <svg [lucide]="icons.ChevronUp" class="h-3 w-3"></svg>
                } @else {
                  <svg [lucide]="icons.ChevronDown" class="h-3 w-3"></svg>
                }
              </button>
            }
            @if (isProcessing() && onCancel()) {
              <button
                type="button"
                (click)="onCancel()?.()"
                aria-label="Cancelar generación"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium text-rose-700 hover:text-rose-800 bg-rose-50 border border-rose-200 hover:bg-rose-100 transition-colors"
              >
                <svg [lucide]="icons.Square" class="h-2.5 w-2.5 fill-rose-700 text-rose-700"></svg>
                <span>Cancelar</span>
              </button>
            }
          </div>
        </div>

        @if (isExpanded()) {
          <div class="mt-2 pt-2 border-t border-slate-200/80 flex flex-col gap-2">
            <!-- TimelineStepList -->
            @if (steps().length > 0) {
              <div class="flex flex-col gap-1.5 pl-1">
                @for (step of steps(); track step.stepId) {
                  <div class="flex items-start gap-2">
                    @if (step.status === 'completed') {
                      <svg [lucide]="icons.CheckCircle2" class="h-3.5 w-3.5 text-emerald-600 mt-0.5 flex-shrink-0"></svg>
                    } @else if (step.status === 'failed') {
                      <svg [lucide]="icons.XCircle" class="h-3.5 w-3.5 text-rose-600 mt-0.5 flex-shrink-0"></svg>
                    } @else {
                      <svg
                        [lucide]="icons.Loader2"
                        class="h-3.5 w-3.5 animate-spin text-[#002777] mt-0.5 flex-shrink-0"
                      ></svg>
                    }
                    <div class="flex flex-col">
                      <span
                        [class]="
                          'text-[11px] ' +
                          (step.status === 'in_progress'
                            ? 'font-semibold text-slate-900'
                            : step.status === 'failed'
                              ? 'text-rose-700 font-medium'
                              : 'text-slate-600')
                        "
                        >{{ step.label }}</span
                      >
                      @if (step.details) {
                        <span class="text-[10px] text-slate-500">{{ step.details }}</span>
                      }
                    </div>
                  </div>
                }
              </div>
            }
            <!-- TimelineSourcesList -->
            @if (sources().length > 0) {
              <div class="mt-1 pt-1.5 border-t border-slate-200/60">
                <div class="flex items-center gap-1.5 mb-1 text-[10px] font-semibold text-slate-500">
                  <svg [lucide]="icons.Database" class="h-3 w-3 text-sky-600"></svg>
                  <span>Fuentes RAG consultadas en tiempo real:</span>
                </div>
                <div class="flex flex-wrap gap-1">
                  @for (src of sources(); track src.sourceId) {
                    <span
                      [title]="src.snippet || src.title"
                      class="inline-flex items-center px-1.5 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 text-[10px] font-medium max-w-[200px] truncate"
                      >{{ src.title }}</span
                    >
                  }
                </div>
              </div>
            }
          </div>
        }
      </div>
    }
  `,
})
export class AgenticThinkingBubbleComponent {
  readonly status = input<string>('Pensando...')
  readonly isProcessing = input<boolean>(true)
  readonly steps = input<AgentRunStep[]>([])
  readonly sources = input<AgentRunSource[]>([])
  readonly onCancel = input<(() => void) | undefined>(undefined)
  readonly isCancelled = input<boolean>(false)

  protected readonly isExpanded = signal(false)
  protected readonly icons = { CheckCircle2, ChevronDown, ChevronUp, Database, Loader2, Square, XCircle }

  protected readonly isVisible = computed(() => !(!this.isProcessing() && this.steps().length === 0 && !this.isCancelled()))
  protected readonly hasTimeline = computed(() => this.steps().length > 0 || this.sources().length > 0)
}
