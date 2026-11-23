import { ChangeDetectionStrategy, Component, input, output } from '@angular/core'
import { Loader2, Star, VolumeX } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { TranscriptionSegment } from '../api/transcriptionApi'
import { formatTimestamp, getSpeakerColor } from '../utils/transcriptionFormatting'

/** Port of React `SegmentList`. */
@Component({
  selector: 'app-segment-list',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @let segs = segments();
    @if (!segs?.length && !plainText()) {
      <!-- Empty state / Loading before any segments arrive -->
      @if (isJobActive()) {
        <div class="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
          <svg [lucide]="icons.Loader2" class="h-8 w-8 animate-spin text-[#002777]"></svg>
          <p class="text-xs font-bold text-slate-700">Procesando...</p>
          <p class="text-[11px] text-slate-400 max-w-xs">
            Los segmentos y la identificación de interlocutores aparecerán aquí a medida que se reconozcan.
          </p>
        </div>
      } @else {
        <div class="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
          <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
            <svg [lucide]="icons.VolumeX" class="h-6 w-6"></svg>
          </div>
          <p class="text-xs font-bold text-slate-700">No se detectaron diálogos en la grabación.</p>
          <p class="text-[11px] text-slate-400 max-w-xs">
            El archivo procesado no contiene voz audible o segmentos de audio para transcribir.
          </p>
        </div>
      }
    } @else if (segs && segs.length > 0) {
      <!-- Render segments (real-time stream or finished) -->
      <div class="space-y-3 max-w-3xl animate-fade-in">
        <p class="text-[11px] text-slate-400 italic mb-2">
          * Haz clic en cualquier segmento para marcarlo o desmarcarlo como <strong>importante</strong>.
        </p>

        @for (seg of segs; track $index; let idx = $index) {
          @let isImportant = importantSegments().has(idx);
          @let speakerColorClass = getSpeakerColor(seg.speaker || 'Participante');
          @let isLatestInLiveJob = isJobActive() && idx === segs.length - 1;
          <div
            (click)="onToggleImportance.emit(idx)"
            [class]="
              'group relative p-3.5 rounded-2xl border transition-all duration-150 cursor-pointer ' +
              (isImportant
                ? 'bg-amber-50/70 border-amber-300 ring-1 ring-amber-200/80 shadow-xs'
                : isLatestInLiveJob
                  ? 'bg-blue-50/40 border-blue-300/80 shadow-xs ring-1 ring-blue-200/50'
                  : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 shadow-2xs')
            "
          >
            <!-- Segment Header -->
            <div class="flex items-center justify-between gap-2 mb-1.5">
              <div class="flex items-center gap-2">
                <span [class]="'px-2.5 py-0.5 rounded-lg text-xs font-bold border shadow-2xs ' + speakerColorClass">{{
                  seg.speaker || 'Participante'
                }}</span>
                <span class="text-[11px] font-mono font-medium text-slate-400">[{{ formatTimestamp(seg.start) }}]</span>
                @if (isLatestInLiveJob) {
                  <span
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-blue-100 text-blue-800"
                  >
                    <span class="h-1.5 w-1.5 rounded-full bg-blue-600 animate-ping"></span>
                    En vivo
                  </span>
                }
              </div>

              <!-- Star / Bookmark Icon -->
              <div class="flex items-center gap-1.5">
                @if (isImportant) {
                  <span
                    class="text-[10px] font-bold uppercase tracking-wider text-amber-800 bg-amber-100 px-2 py-0.5 rounded-md"
                  >
                    Importante
                  </span>
                }
                <button
                  type="button"
                  (click)="$event.stopPropagation(); onToggleImportance.emit(idx)"
                  [class]="
                    'p-1 rounded-lg transition ' +
                    (isImportant
                      ? 'text-amber-500 hover:text-amber-600'
                      : 'text-slate-300 group-hover:text-slate-400 hover:text-amber-500')
                  "
                  [title]="isImportant ? 'Desmarcar de importante' : 'Marcar como importante'"
                >
                  <svg
                    [lucide]="icons.Star"
                    [class]="'h-4 w-4 ' + (isImportant ? 'fill-amber-400 text-amber-500' : '')"
                  ></svg>
                </button>
              </div>
            </div>

            <!-- Dialogue text -->
            <p
              [class]="'text-sm leading-relaxed ' + (isImportant ? 'font-semibold text-slate-900' : 'text-slate-700')"
            >{{ seg.text }}@if (isLatestInLiveJob) {<span class="inline-block w-1.5 h-4 ml-1 bg-[#002777] animate-pulse align-middle"></span>}</p>
          </div>
        }

        <!-- Live Streaming Indicator at the bottom of the list -->
        @if (isJobActive()) {
          <div
            class="flex items-center gap-2.5 px-4 py-3 rounded-2xl bg-blue-50/80 border border-blue-200/80 text-xs text-[#002777] shadow-2xs animate-pulse"
          >
            <svg [lucide]="icons.Loader2" class="h-4 w-4 animate-spin text-[#002777]"></svg>
            <span class="font-semibold">{{
              activeProgressMessage() || 'Transcribiendo siguientes turnos de voz en vivo...'
            }}</span>
          </div>
        }
      </div>
    } @else {
      <!-- Render plain text fallback -->
      <div
        class="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap"
      >{{ plainText() }}</div>
    }
  `,
})
export class SegmentListComponent {
  readonly segments = input<TranscriptionSegment[] | undefined>(undefined)
  readonly plainText = input<string | undefined>(undefined)
  readonly importantSegments = input.required<Set<number>>()
  readonly activeProgressMessage = input<string | undefined>(undefined)
  readonly isJobActive = input<boolean | undefined>(undefined)

  readonly onToggleImportance = output<number>()

  protected readonly icons = { Loader2, Star, VolumeX }
  protected readonly formatTimestamp = formatTimestamp
  protected readonly getSpeakerColor = getSpeakerColor
}
