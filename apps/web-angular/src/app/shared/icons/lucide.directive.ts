import { Directive, ElementRef, Renderer2, effect, inject, input } from '@angular/core'
import type { IconNode } from 'lucide'

const SVG_NS = 'http://www.w3.org/2000/svg'

/**
 * Renders a Lucide icon directly into the host `<svg>` element.
 *
 * Replaces `lucide-react` with identical markup: same default attributes and the classes stay on
 * the `<svg>` itself, so Tailwind sizing/color classes copied from the React JSX behave exactly the same.
 *
 * Usage:
 *   import { Sparkles } from 'lucide'
 *   protected readonly icons = { Sparkles }
 *   <svg [lucide]="icons.Sparkles" class="h-4 w-4 text-white"></svg>
 *
 * `size` and `strokeWidth` mirror the lucide-react props of the same name.
 */
@Directive({
  selector: 'svg[lucide]',
})
export class LucideIconDirective {
  readonly lucide = input.required<IconNode>()
  readonly size = input<number | string>(24)
  readonly strokeWidth = input<number | string>(2)

  private readonly host = inject<ElementRef<SVGSVGElement>>(ElementRef)
  private readonly renderer = inject(Renderer2)

  constructor() {
    effect(() => {
      const node = this.lucide()
      const size = String(this.size())
      const strokeWidth = String(this.strokeWidth())
      this.render(node, size, strokeWidth)
    })
  }

  private render(node: IconNode, size: string, strokeWidth: string): void {
    const svg = this.host.nativeElement
    const attrs: Record<string, string> = {
      xmlns: SVG_NS,
      width: size,
      height: size,
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': strokeWidth,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    }
    for (const [name, value] of Object.entries(attrs)) {
      this.renderer.setAttribute(svg, name, value)
    }
    // lucide-react marks decorative icons as hidden from assistive tech unless labelled.
    if (!svg.hasAttribute('aria-label') && !svg.hasAttribute('aria-hidden')) {
      this.renderer.setAttribute(svg, 'aria-hidden', 'true')
    }

    while (svg.firstChild) svg.removeChild(svg.firstChild)
    for (const [tag, childAttrs] of node ?? []) {
      const child = this.renderer.createElement(tag, 'svg') as SVGElement
      for (const [name, value] of Object.entries(childAttrs ?? {})) {
        if (value === undefined || value === null) continue
        this.renderer.setAttribute(child, name, String(value))
      }
      this.renderer.appendChild(svg, child)
    }
  }
}
