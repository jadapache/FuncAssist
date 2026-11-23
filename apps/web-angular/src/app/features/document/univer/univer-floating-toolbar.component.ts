/**
 * univer-floating-toolbar.component.ts
 * Port of React `UniverFloatingToolbar.tsx`: ultra-responsive floating WYSIWYG toolbar for the Univer container.
 * Rounded-full pill container with px-4 framing to completely prevent icon clipping at curved ends.
 */

import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core'
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  ChevronDown,
  Indent,
  Italic,
  List,
  ListOrdered,
  Minus,
  MoreVertical,
  Outdent,
  Plus,
  Redo2,
  Type,
  Underline,
  Undo2,
} from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { UniverAlignment, UniverMode } from './univer-blocks'

const TEXT_COLORS = [
  { label: 'Azul Corporativo', value: '#002777' },
  { label: 'Negro Slate', value: '#0f172a' },
  { label: 'Gris Oscuro', value: '#334155' },
  { label: 'Azul Marino', value: '#1e3a8a' },
  { label: 'Verde Esmeralda', value: '#047857' },
  { label: 'Rojo Carmín', value: '#b91c1c' },
  { label: 'Púrpura', value: '#6b21a8' },
]

@Component({
  selector: 'app-univer-floating-toolbar',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div #wrapper class="w-full flex flex-col items-center gap-1 select-none my-0.5 transition-all">
      <!-- 1. DYNAMIC PRIMARY FLOATING TOOLBAR -->
      <div
        class="relative z-20 bg-white/95 backdrop-blur-md border border-slate-300/90 shadow-lg rounded-full px-2.5 py-0.5 flex items-center justify-center gap-0.5 text-slate-700 h-9 shrink-0 max-w-full"
      >
        <!-- 1. Zoom Selector (First element on the left) -->
        <div class="flex items-center shrink-0">
          <select
            [value]="zoom()"
            (change)="handleZoomSelect($event)"
            class="h-7.5 bg-transparent hover:bg-slate-100 text-xs font-semibold px-0.5 rounded-md border-0 focus:outline-hidden cursor-pointer text-slate-700"
            title="Zoom de página"
          >
            <option value="50">50%</option>
            <option value="75">75%</option>
            <option value="100">100%</option>
            <option value="125">125%</option>
            <option value="150">150%</option>
          </select>
        </div>

        <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>

        <!-- Deshacer / Rehacer -->
        <button
          type="button"
          (click)="onUndo.emit()"
          [disabled]="!canUndo()"
          class="h-7.5 w-6 rounded-full hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent text-slate-700 flex items-center justify-center transition cursor-pointer shrink-0"
          title="Deshacer (Ctrl+Z)"
        >
          <svg [lucide]="icons.Undo2" class="h-3.5 w-3.5"></svg>
        </button>

        <button
          type="button"
          (click)="onRedo.emit()"
          [disabled]="!canRedo()"
          class="h-7.5 w-6 rounded-full hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent text-slate-700 flex items-center justify-center transition cursor-pointer shrink-0"
          title="Rehacer (Ctrl+Y)"
        >
          <svg [lucide]="icons.Redo2" class="h-3.5 w-3.5"></svg>
        </button>

        <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>

        <!-- Text Style Dropdown -->
        <div class="relative shrink-0">
          <select
            [value]="textStyle()"
            (change)="handleTextStyleSelect($event)"
            [class]="
              'h-7.5 bg-transparent hover:bg-slate-100 text-xs font-bold text-[#002777] px-0.5 rounded-md border-0 focus:outline-hidden cursor-pointer truncate transition-all ' +
              (isXl() ? 'w-[84px]' : isLg() ? 'w-[76px]' : isMd() ? 'w-[68px]' : isSm() ? 'w-[60px]' : 'w-[52px]')
            "
          >
            <option value="paragraph">Normal</option>
            <option value="h1">Título</option>
            <option value="h2">Subtítulo</option>
          </select>
        </div>

        <!-- Font Family Dropdown -->
        <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
        <div class="relative shrink-0">
          <select
            [value]="fontFamily()"
            (change)="handleFontFamilySelect($event)"
            [class]="
              'h-7.5 bg-transparent hover:bg-slate-100 text-xs font-semibold px-0.5 rounded-md border-0 focus:outline-hidden cursor-pointer truncate transition-all ' +
              (isXl() ? 'w-[76px]' : isLg() ? 'w-[68px]' : isMd() ? 'w-[60px]' : isSm() ? 'w-[52px]' : 'w-[44px]')
            "
            title="Fuente"
          >
            <option value="Arial">Arial</option>
            <option value="Inter">Inter</option>
            <option value="Roboto">Roboto</option>
            <option value="Times New Roman">Times</option>
            <option value="Courier New">Courier</option>
            <option value="Georgia">Georgia</option>
          </select>
        </div>

        <!-- Font Size Selector (- 13 +) (Visible if width >= 500px) -->
        @if (isMd()) {
          <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
          <div class="flex items-center h-7.5 shrink-0">
            <button
              type="button"
              (click)="onFontSizeChange.emit(max(8, fontSize() - 1))"
              class="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
              title="Disminuir tamaño"
            >
              <svg [lucide]="icons.Minus" class="h-3 w-3"></svg>
            </button>
            <span class="w-5 text-center font-mono text-xs font-bold text-slate-800">{{ fontSize() }}</span>
            <button
              type="button"
              (click)="onFontSizeChange.emit(min(36, fontSize() + 1))"
              class="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
              title="Aumentar tamaño"
            >
              <svg [lucide]="icons.Plus" class="h-3 w-3"></svg>
            </button>
          </div>
        }

        <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>

        <!-- Bold, Italic & Underline Buttons -->
        <div class="flex items-center gap-0.5 shrink-0">
          <button
            type="button"
            (click)="onToggleBold.emit()"
            [class]="
              'h-7.5 w-5.5 rounded-md font-bold text-xs flex items-center justify-center transition cursor-pointer shrink-0 ' +
              (isBold() ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100')
            "
            title="Negrita (Ctrl+B)"
          >
            <svg [lucide]="icons.Bold" class="h-3.5 w-3.5"></svg>
          </button>

          <button
            type="button"
            (click)="onToggleItalic.emit()"
            [class]="
              'h-7.5 w-5.5 rounded-md italic text-xs flex items-center justify-center transition cursor-pointer shrink-0 ' +
              (isItalic() ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100')
            "
            title="Cursiva (Ctrl+I)"
          >
            <svg [lucide]="icons.Italic" class="h-3.5 w-3.5"></svg>
          </button>

          <button
            type="button"
            (click)="onToggleUnderline.emit()"
            [class]="
              'h-7.5 w-5.5 rounded-md underline text-xs flex items-center justify-center transition cursor-pointer shrink-0 ' +
              (isUnderline() ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100')
            "
            title="Subrayado (Ctrl+U)"
          >
            <svg [lucide]="icons.Underline" class="h-3.5 w-3.5"></svg>
          </button>
        </div>

        <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>

        <!-- Color de Texto -->
        <div class="relative shrink-0">
          <button
            type="button"
            (click)="showColorPicker.set(!showColorPicker()); showAlignPicker.set(false)"
            [class]="
              'h-7.5 w-5.5 rounded-md flex flex-col items-center justify-center transition cursor-pointer shrink-0 ' +
              (showColorPicker() ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100')
            "
            title="Color de texto"
          >
            <svg [lucide]="icons.Type" class="h-3.5 w-3.5"></svg>
            <div class="h-0.5 w-3 rounded-full mt-0.5" [style.background-color]="textColor()"></div>
          </button>

          @if (showColorPicker()) {
            <div
              class="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl p-2 z-50 flex flex-col gap-1 w-44"
            >
              <span class="text-[10px] font-bold text-slate-400 uppercase px-1">Color de texto</span>
              @for (c of textColors; track c.value) {
                <button
                  type="button"
                  (click)="onTextColorChange.emit(c.value); showColorPicker.set(false)"
                  class="flex items-center gap-2 px-2 py-1 rounded text-xs hover:bg-slate-50 cursor-pointer"
                >
                  <div class="h-3.5 w-3.5 rounded-full border border-slate-300" [style.background-color]="c.value"></div>
                  <span class="text-slate-700 font-medium text-xs">{{ c.label }}</span>
                </button>
              }
            </div>
          }
        </div>

        <!-- Grouped Alignment Dropdown (Visible on primary bar if width >= 440px) -->
        @if (isSm()) {
          <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
          <div class="relative shrink-0">
            <button
              type="button"
              (click)="showAlignPicker.set(!showAlignPicker()); showColorPicker.set(false)"
              [class]="
                'h-7.5 px-1 rounded-lg transition cursor-pointer flex items-center gap-0.5 ' +
                (showAlignPicker() ? 'bg-blue-100 text-[#002777]' : 'hover:bg-slate-100 text-slate-700')
              "
              title="Alineación de texto"
            >
              <svg [lucide]="alignIcon()" class="h-3.5 w-3.5"></svg>
              <svg [lucide]="icons.ChevronDown" class="h-3 w-3 text-slate-500"></svg>
            </button>

            @if (showAlignPicker()) {
              <div
                class="absolute left-1/2 -translate-x-1/2 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl p-1 z-50 flex flex-col gap-0.5 w-11 items-center"
              >
                <button
                  type="button"
                  (click)="onAlignmentChange.emit('left'); showAlignPicker.set(false)"
                  [class]="
                    'p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ' +
                    (alignment() === 'left' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700')
                  "
                  title="Alinear a la izquierda"
                >
                  <svg [lucide]="icons.AlignLeft" class="h-4 w-4"></svg>
                </button>

                <button
                  type="button"
                  (click)="onAlignmentChange.emit('center'); showAlignPicker.set(false)"
                  [class]="
                    'p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ' +
                    (alignment() === 'center' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700')
                  "
                  title="Centrar"
                >
                  <svg [lucide]="icons.AlignCenter" class="h-4 w-4"></svg>
                </button>

                <button
                  type="button"
                  (click)="onAlignmentChange.emit('right'); showAlignPicker.set(false)"
                  [class]="
                    'p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ' +
                    (alignment() === 'right' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700')
                  "
                  title="Alinear a la derecha"
                >
                  <svg [lucide]="icons.AlignRight" class="h-4 w-4"></svg>
                </button>

                <button
                  type="button"
                  (click)="onAlignmentChange.emit('justify'); showAlignPicker.set(false)"
                  [class]="
                    'p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ' +
                    (alignment() === 'justify' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700')
                  "
                  title="Justificar"
                >
                  <svg [lucide]="icons.AlignJustify" class="h-4 w-4"></svg>
                </button>
              </div>
            }
          </div>
        }

        <!-- Lists (Visible on primary bar if width >= 680px) -->
        @if (isXl()) {
          <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
          <div class="flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              (click)="onToggleBulletList.emit()"
              class="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
              title="Lista de viñetas"
            >
              <svg [lucide]="icons.List" class="h-3.5 w-3.5"></svg>
            </button>
            <button
              type="button"
              (click)="onToggleNumberedList.emit()"
              class="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
              title="Lista numerada"
            >
              <svg [lucide]="icons.ListOrdered" class="h-3.5 w-3.5"></svg>
            </button>
          </div>
        }

        <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>

        <!-- 3-DOTS MORE OPTIONS BUTTON -->
        <button
          type="button"
          (click)="showMoreMenu.set(!showMoreMenu())"
          [class]="
            'h-7.5 w-7.5 rounded-full transition cursor-pointer flex items-center justify-center shrink-0 ' +
            (showMoreMenu() ? 'bg-blue-100 text-[#002777]' : 'hover:bg-slate-100 text-slate-700')
          "
          title="Más opciones de formato"
        >
          <svg [lucide]="icons.MoreVertical" class="h-4 w-4"></svg>
        </button>
      </div>

      <!-- 2. DYNAMIC HORIZONTAL SUB-TOOLBAR EXTENSION BAR (Shows items moved from primary bar + indents & zoom) -->
      @if (showMoreMenu()) {
        <div
          class="relative z-10 bg-white/95 backdrop-blur-md border border-slate-300/90 shadow-lg rounded-full px-3 py-0.5 flex flex-wrap items-center justify-center gap-1 min-h-9 max-w-full text-slate-700 shrink-0 animate-fadeIn transition-all"
        >
          <!-- Alignment (Moved to 3-dots if width < 440px) -->
          @if (!isSm()) {
            <div class="relative shrink-0">
              <button
                type="button"
                (click)="showAlignPicker.set(!showAlignPicker())"
                [class]="
                  'h-7.5 px-1.5 rounded-lg transition cursor-pointer flex items-center gap-0.5 ' +
                  (showAlignPicker() ? 'bg-blue-100 text-[#002777]' : 'hover:bg-slate-100 text-slate-700')
                "
                title="Alineación de texto"
              >
                <svg [lucide]="alignIcon()" class="h-3.5 w-3.5"></svg>
                <svg [lucide]="icons.ChevronDown" class="h-3 w-3 text-slate-500"></svg>
              </button>
            </div>
            <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
          }

          <!-- Font Size Selector (Moved to 3-dots if width < 500px) -->
          @if (!isMd()) {
            <div class="flex items-center h-7.5 shrink-0">
              <button
                type="button"
                (click)="onFontSizeChange.emit(max(8, fontSize() - 1))"
                class="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
                title="Disminuir tamaño"
              >
                <svg [lucide]="icons.Minus" class="h-3 w-3"></svg>
              </button>
              <span class="w-5 text-center font-mono text-xs font-bold text-slate-800">{{ fontSize() }}</span>
              <button
                type="button"
                (click)="onFontSizeChange.emit(min(36, fontSize() + 1))"
                class="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
                title="Aumentar tamaño"
              >
                <svg [lucide]="icons.Plus" class="h-3 w-3"></svg>
              </button>
            </div>
            <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
          }

          <!-- Listas (Moved to 3-dots if width < 720px) -->
          @if (!isXl()) {
            <div class="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                (click)="onToggleBulletList.emit()"
                class="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
                title="Lista de viñetas"
              >
                <svg [lucide]="icons.List" class="h-3.5 w-3.5"></svg>
              </button>
              <button
                type="button"
                (click)="onToggleNumberedList.emit()"
                class="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
                title="Lista numerada"
              >
                <svg [lucide]="icons.ListOrdered" class="h-3.5 w-3.5"></svg>
              </button>
            </div>
            <div class="h-4 w-px bg-slate-200 mx-0.5 shrink-0"></div>
          }

          <!-- Sangría (Always in 3-dots) -->
          <div class="flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              (click)="onOutdent.emit()"
              class="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
              title="Disminuir sangría"
            >
              <svg [lucide]="icons.Outdent" class="h-3.5 w-3.5"></svg>
            </button>

            <button
              type="button"
              (click)="onIndent.emit()"
              class="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
              title="Aumentar sangría"
            >
              <svg [lucide]="icons.Indent" class="h-3.5 w-3.5"></svg>
            </button>
          </div>
        </div>
      }
    </div>
  `,
})
export class UniverFloatingToolbarComponent {
  readonly zoom = input.required<number>()
  readonly canUndo = input.required<boolean>()
  readonly canRedo = input.required<boolean>()
  readonly textStyle = input.required<string>()
  readonly fontFamily = input.required<string>()
  readonly fontSize = input.required<number>()
  readonly isBold = input.required<boolean>()
  readonly isItalic = input.required<boolean>()
  readonly isUnderline = input.required<boolean>()
  readonly textColor = input.required<string>()
  readonly alignment = input.required<UniverAlignment>()
  /** Accepted for API parity with React (the React toolbar also ignores it). */
  readonly mode = input<UniverMode | undefined>(undefined)

  readonly onZoomChange = output<number>()
  readonly onUndo = output<void>()
  readonly onRedo = output<void>()
  readonly onTextStyleChange = output<string>()
  readonly onFontFamilyChange = output<string>()
  readonly onFontSizeChange = output<number>()
  readonly onToggleBold = output<void>()
  readonly onToggleItalic = output<void>()
  readonly onToggleUnderline = output<void>()
  readonly onTextColorChange = output<string>()
  readonly onAlignmentChange = output<UniverAlignment>()
  readonly onToggleBulletList = output<void>()
  readonly onToggleNumberedList = output<void>()
  readonly onIndent = output<void>()
  readonly onOutdent = output<void>()

  protected readonly icons = {
    Undo2,
    Redo2,
    ChevronDown,
    Minus,
    Plus,
    Bold,
    Italic,
    Underline,
    AlignLeft,
    AlignCenter,
    AlignRight,
    AlignJustify,
    List,
    ListOrdered,
    Indent,
    Outdent,
    Type,
    MoreVertical,
  }
  protected readonly textColors = TEXT_COLORS
  protected readonly max = Math.max
  protected readonly min = Math.min

  private readonly wrapperRef = viewChild.required<ElementRef<HTMLDivElement>>('wrapper')
  private readonly hostRef = inject<ElementRef<HTMLElement>>(ElementRef)
  private readonly injector = inject(Injector)
  private readonly destroyRef = inject(DestroyRef)

  protected readonly containerWidth = signal<number>(800)
  protected readonly showColorPicker = signal(false)
  protected readonly showAlignPicker = signal(false)
  protected readonly showMoreMenu = signal(false)

  // Responsive container width tiers:
  protected readonly isXl = computed(() => this.containerWidth() >= 760)
  protected readonly isLg = computed(() => this.containerWidth() >= 620)
  protected readonly isMd = computed(() => this.containerWidth() >= 500)
  protected readonly isSm = computed(() => this.containerWidth() >= 440)

  protected readonly alignIcon = computed(() => {
    const alignment = this.alignment()
    return alignment === 'center'
      ? AlignCenter
      : alignment === 'right'
        ? AlignRight
        : alignment === 'justify'
          ? AlignJustify
          : AlignLeft
  })

  constructor() {
    // Measure actual container pixel width via ResizeObserver (measures parent canvas viewport width)
    afterNextRender(() => {
      const wrapper = this.wrapperRef().nativeElement
      const host = this.hostRef.nativeElement
      // The host element uses `display: contents`, so the React parent element is the host's parent.
      const directParent = wrapper.parentElement === host ? host.parentElement : wrapper.parentElement
      const parentEl = directParent || wrapper

      const updateWidth = () => {
        const measured = parentEl.clientWidth || parentEl.offsetWidth || 800
        this.containerWidth.set(measured)
      }

      updateWidth()

      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          if (entry.contentRect && entry.contentRect.width > 0) {
            this.containerWidth.set(entry.contentRect.width)
          }
        }
      })

      observer.observe(parentEl)
      this.destroyRef.onDestroy(() => observer.disconnect())
    })
  }

  protected handleZoomSelect(event: Event): void {
    const el = event.target as HTMLSelectElement
    this.onZoomChange.emit(Number(el.value))
    this.syncControlledSelect(el, () => this.zoom())
  }

  protected handleTextStyleSelect(event: Event): void {
    const el = event.target as HTMLSelectElement
    this.onTextStyleChange.emit(el.value)
    this.syncControlledSelect(el, () => this.textStyle())
  }

  protected handleFontFamilySelect(event: Event): void {
    const el = event.target as HTMLSelectElement
    this.onFontFamilyChange.emit(el.value)
    this.syncControlledSelect(el, () => this.fontFamily())
  }

  /**
   * React `<select value={x}>` is controlled: after the change handler runs, the DOM value is reset to the prop.
   * Angular only writes `[value]` when the bound value changes, so re-apply it after the next render.
   */
  private syncControlledSelect(el: HTMLSelectElement, controlled: () => string | number): void {
    afterNextRender(
      {
        write: () => {
          const value = String(controlled())
          if (el.value !== value) el.value = value
        },
      },
      { injector: this.injector },
    )
  }
}
