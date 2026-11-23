import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  input,
  output,
  viewChild,
} from '@angular/core'
import { ChevronDown, Download, FileText } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { RefObject } from '../utils/reactCompat'

export interface DownloadItem {
  label: string
  description: string
  icon: 'text' | 'json'
  color: 'blue' | 'amber'
  onSelect: () => void
}

/** Port of React `DownloadMenu`. `menuRef` is filled with the root element (React `ref={menuRef}`). */
@Component({
  selector: 'app-download-menu',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="relative" #root>
      <button
        type="button"
        (click)="onToggle.emit()"
        [disabled]="disabled()"
        class="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center gap-0.5"
        [title]="title()"
      >
        <svg [lucide]="icons.Download" class="h-3.5 w-3.5 text-slate-500"></svg>
        <svg [lucide]="icons.ChevronDown" class="h-3 w-3 text-slate-400"></svg>
      </button>

      @if (isOpen()) {
        <div
          class="absolute right-0 top-full mt-1.5 w-44 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-30 animate-scale-in"
        >
          @for (item of items(); track $index) {
            <button
              type="button"
              (click)="item.onSelect()"
              class="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-[#002777] flex items-center gap-2 transition cursor-pointer"
            >
              <svg [lucide]="icons.FileText" [class]="'h-3.5 w-3.5 ' + colorMap[item.color]"></svg>
              <div>
                <div class="font-bold">{{ item.label }}</div>
                <div class="text-[10px] text-slate-400">{{ item.description }}</div>
              </div>
            </button>
          }
        </div>
      }
    </div>
  `,
})
export class DownloadMenuComponent {
  readonly menuRef = input<RefObject<HTMLDivElement | null> | undefined>(undefined)
  readonly isOpen = input(false)
  readonly items = input<DownloadItem[]>([])
  readonly disabled = input(false)
  readonly title = input('Descargar')

  readonly onToggle = output<void>()

  protected readonly icons = { ChevronDown, Download, FileText }
  protected readonly colorMap: Record<DownloadItem['color'], string> = {
    blue: 'text-blue-600',
    amber: 'text-amber-600',
  }

  private readonly root = viewChild<ElementRef<HTMLDivElement>>('root')

  constructor() {
    effect((onCleanup) => {
      const ref = this.menuRef()
      const el = this.root()?.nativeElement
      if (!ref || !el) return
      ref.current = el
      onCleanup(() => {
        if (ref.current === el) ref.current = null
      })
    })
    inject(DestroyRef).onDestroy(() => {
      const ref = this.menuRef()
      if (ref) ref.current = null
    })
  }
}
