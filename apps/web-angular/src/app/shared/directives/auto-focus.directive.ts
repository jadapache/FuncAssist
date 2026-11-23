import { Directive, ElementRef, afterNextRender, inject } from '@angular/core'

/** Equivalent of the React `autoFocus` prop: focuses the element right after it is rendered. */
@Directive({
  selector: '[appAutoFocus]',
})
export class AutoFocusDirective {
  constructor() {
    const el = inject<ElementRef<HTMLElement>>(ElementRef)
    afterNextRender(() => el.nativeElement.focus())
  }
}
