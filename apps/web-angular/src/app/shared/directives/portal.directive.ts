import { Directive, ElementRef, OnDestroy, OnInit, inject } from '@angular/core'

/**
 * Equivalent of React `createPortal(node, document.body)`.
 *
 * Moves the host element to <body> while keeping all Angular bindings alive. Use it on overlays
 * (modals, dropdown menus) whose `fixed` positioning would otherwise be trapped by an ancestor with
 * `transform`, `filter` or `overflow: hidden` — exactly the cases where the React code used a portal.
 *
 *   <div appPortal class="fixed inset-0 z-50 ...">...</div>
 */
@Directive({
  selector: '[appPortal]',
})
export class PortalDirective implements OnInit, OnDestroy {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef)

  ngOnInit(): void {
    document.body.appendChild(this.host.nativeElement)
  }

  ngOnDestroy(): void {
    this.host.nativeElement.remove()
  }
}
