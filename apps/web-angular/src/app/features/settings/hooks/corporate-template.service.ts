import { DestroyRef, Injectable, inject, signal } from '@angular/core'
import { api, type CorporateTemplate } from '../../../api/client'

/**
 * Angular port of React `useCorporateTemplate(moduleSlug, defaultFallback)`.
 * Loads the corporate template matching the module slug (or the first available one) and exposes
 * its content, falling back to `defaultFallback` when none can be loaded.
 *
 * Per-component state → `@Injectable()` without `providedIn`: list it in the consumer's `providers`
 * and call `init(moduleSlug, defaultFallback)` (again whenever the slug changes, like the React effect).
 */
@Injectable()
export class CorporateTemplateService {
  private readonly _templateContent = signal<string>('')
  private readonly _activeTemplate = signal<CorporateTemplate | null>(null)
  private readonly _loadingTemplate = signal<boolean>(true)

  readonly templateContent = this._templateContent.asReadonly()
  readonly activeTemplate = this._activeTemplate.asReadonly()
  readonly loadingTemplate = this._loadingTemplate.asReadonly()

  private generation = 0
  private initialized = false
  private destroyed = false
  private moduleSlug: string | null = null

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      this.destroyed = true
    })
  }

  /** Hook parameters. Re-fetches only when `moduleSlug` changes (React effect deps: `[moduleSlug]`). */
  init(moduleSlug: string, defaultFallback: string): void {
    if (!this.initialized) {
      // React: useState<string>(defaultFallback) — only the first value is used as initial state.
      this._templateContent.set(defaultFallback)
      this.initialized = true
    }
    if (this.moduleSlug === moduleSlug) return
    this.moduleSlug = moduleSlug
    void this.fetchTemplate(moduleSlug)
  }

  private async fetchTemplate(moduleSlug: string): Promise<void> {
    const generation = ++this.generation
    const isMounted = () => !this.destroyed && generation === this.generation

    this._loadingTemplate.set(true)
    try {
      const res = await api.getTemplates()
      const templates = res.templates || []

      // Search for a template matching the module slug or fallback to first available
      const matched = templates.find((t) => t.module?.toLowerCase() === moduleSlug.toLowerCase()) || templates[0]

      if (matched && isMounted()) {
        this._activeTemplate.set(matched)
        const detail = await api.getTemplateContent(matched.id)
        if (detail.content && isMounted()) {
          this._templateContent.set(detail.content)
        }
      }
    } catch (err) {
      console.warn('Could not load corporate template from backend, using fallback:', err)
    } finally {
      if (isMounted()) this._loadingTemplate.set(false)
    }
  }
}
