import {
  Directive,
  ElementRef,
  InjectionToken,
  NgZone,
  afterRenderEffect,
  inject,
  input,
  output,
} from '@angular/core'
import { Tag, X, type IconNode } from 'lucide'
import { splitRichInlineText, type RichInlinePart, type UniverMode } from './univer-blocks'

/** Receives errors thrown while rendering (replacement for the React error boundary catching render errors). */
export interface UniverRenderErrorReporter {
  reportRenderError(error: unknown): void
}

export const UNIVER_RENDER_ERROR_REPORTER = new InjectionToken<UniverRenderErrorReporter>('UNIVER_RENDER_ERROR_REPORTER')

const SVG_NS = 'http://www.w3.org/2000/svg'

const TAG_CHIP_CLASS =
  'inline-flex items-center gap-1 px-2.5 py-0.5 mx-1 rounded-full text-xs font-mono font-bold bg-blue-100 text-[#002777] border border-blue-300 shadow-2xs select-none hover:bg-blue-200 transition group/badge'
const TAG_REMOVE_BUTTON_CLASS =
  'ml-0.5 text-blue-400 hover:text-red-600 hover:bg-blue-300/60 rounded-full p-0.5 transition cursor-pointer'

/**
 * Port of React `renderRichInlineText(text, lineIndex, onRemoveTag, mode)`.
 *
 * Renders the inline Markdown of one line (placeholder chips, **bold**, *italic*) as the children of the host.
 * The host is usually a `contenteditable` element whose DOM the browser mutates while the user types, so the
 * children are written imperatively (like React's reconciliation, the DOM is only touched when the rendered
 * output changes). When the focused host is re-rendered the caret offset is restored.
 */
@Directive({
  selector: '[appUniverRichText]',
})
export class UniverRichTextDirective {
  /** Inline Markdown text of the line. */
  readonly appUniverRichText = input<string>('')
  readonly lineIndex = input<number>(0)
  readonly mode = input<UniverMode>('template')
  /** React passed `onRemoveTag` only for document body blocks; header/footer chips have no remove button. */
  readonly removable = input<boolean>(false)
  readonly onRemoveTag = output<{ lineIndex: number; tag: string }>()

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef)
  private readonly zone = inject(NgZone)
  private readonly reporter = inject(UNIVER_RENDER_ERROR_REPORTER, { optional: true })
  private renderedKey: string | null = null

  constructor() {
    afterRenderEffect(() => {
      const text = this.appUniverRichText()
      const mode = this.mode()
      const removable = this.removable()
      const key = `${mode}|${removable ? '1' : '0'}|${text}`
      if (key === this.renderedKey) return

      try {
        const el = this.host.nativeElement
        const caret = captureCaretOffset(el)
        el.replaceChildren(this.buildFragment(splitRichInlineText(text), mode === 'template' && removable))
        this.renderedKey = key
        if (caret !== null) restoreCaretOffset(el, caret)
      } catch (error) {
        this.reporter?.reportRenderError(error)
      }
    })
  }

  private buildFragment(parts: RichInlinePart[], withRemoveButton: boolean): DocumentFragment {
    const doc = this.host.nativeElement.ownerDocument
    const fragment = doc.createDocumentFragment()

    for (const part of parts) {
      if (part.kind === 'tag') {
        const chip = doc.createElement('span')
        chip.className = TAG_CHIP_CLASS
        chip.title = `Placeholder: ${part.text}`
        chip.appendChild(createIcon(doc, Tag, 'h-3 w-3 text-[#002777] shrink-0'))
        const label = doc.createElement('span')
        label.textContent = part.text
        chip.appendChild(label)

        if (withRemoveButton) {
          const button = doc.createElement('button')
          button.type = 'button'
          button.className = TAG_REMOVE_BUTTON_CLASS
          button.title = `Eliminar placeholder ${part.text}`
          button.appendChild(createIcon(doc, X, 'h-3 w-3'))
          const cleanName = part.name
          button.addEventListener('click', (e) => {
            e.stopPropagation()
            this.zone.run(() => this.onRemoveTag.emit({ lineIndex: this.lineIndex(), tag: cleanName }))
          })
          chip.appendChild(button)
        }

        fragment.appendChild(chip)
        continue
      }

      if (part.kind === 'strong') {
        const strong = doc.createElement('strong')
        strong.className = 'font-bold text-slate-900'
        strong.textContent = part.text
        fragment.appendChild(strong)
        continue
      }

      if (part.kind === 'em') {
        const em = doc.createElement('em')
        em.className = 'italic text-slate-800'
        em.textContent = part.text
        fragment.appendChild(em)
        continue
      }

      // React does not create DOM text nodes for empty string children.
      if (part.text) fragment.appendChild(doc.createTextNode(part.text))
    }

    return fragment
  }
}

/** Same SVG markup as `LucideIconDirective` (shared/icons) produces for `<svg [lucide]>`. */
function createIcon(doc: Document, node: IconNode, className: string): SVGSVGElement {
  const svg = doc.createElementNS(SVG_NS, 'svg') as SVGSVGElement
  const attrs: Record<string, string> = {
    xmlns: SVG_NS,
    width: '24',
    height: '24',
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '2',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
    class: className,
  }
  for (const [name, value] of Object.entries(attrs)) {
    svg.setAttribute(name, value)
  }
  for (const [tag, childAttrs] of node ?? []) {
    const child = doc.createElementNS(SVG_NS, tag)
    for (const [name, value] of Object.entries(childAttrs ?? {})) {
      if (value === undefined || value === null) continue
      child.setAttribute(name, String(value))
    }
    svg.appendChild(child)
  }
  return svg
}

/** Character offset of the caret inside `el`, or `null` when `el` is not focused. */
function captureCaretOffset(el: HTMLElement): number | null {
  const doc = el.ownerDocument
  if (doc.activeElement !== el) return null
  const selection = doc.getSelection()
  if (!selection || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)
  if (!el.contains(range.endContainer)) return null
  const pre = doc.createRange()
  pre.selectNodeContents(el)
  pre.setEnd(range.endContainer, range.endOffset)
  return pre.toString().length
}

function restoreCaretOffset(el: HTMLElement, offset: number): void {
  const doc = el.ownerDocument
  const selection = doc.getSelection()
  if (!selection) return

  const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  let remaining = offset
  let target: Text | null = null
  let targetOffset = 0
  let current = walker.nextNode()
  while (current) {
    const length = (current as Text).data.length
    if (remaining <= length) {
      target = current as Text
      targetOffset = remaining
      break
    }
    remaining -= length
    current = walker.nextNode()
  }

  const range = doc.createRange()
  if (target) {
    range.setStart(target, targetOffset)
    range.collapse(true)
  } else {
    range.selectNodeContents(el)
    range.collapse(false)
  }
  selection.removeAllRanges()
  selection.addRange(range)
}
