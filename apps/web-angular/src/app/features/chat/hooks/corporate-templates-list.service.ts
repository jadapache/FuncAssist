import { Injectable, computed, signal } from '@angular/core'
import { api, type CorporateTemplate } from '../../../api/client'

/**
 * Angular port of React `useCorporateTemplatesList`: corporate templates offered in the chat "+" menu,
 * revealed 3 at a time while the list is scrolled. Fetches on creation (React: on mount).
 * Per-component state → `@Injectable()`; list it in the consumer's `providers`.
 */
@Injectable()
export class CorporateTemplatesListService {
  private readonly _corporateTemplates = signal<CorporateTemplate[]>([])
  private readonly visibleTemplateCount = signal(3)
  private readonly _selectedTemplateId = signal<string | null>(null)
  private readonly _templateMenuOpen = signal(false)

  readonly corporateTemplates = this._corporateTemplates.asReadonly()
  readonly selectedTemplateId = this._selectedTemplateId.asReadonly()
  readonly templateMenuOpen = this._templateMenuOpen.asReadonly()

  readonly selectedTemplate = computed(() => {
    const selectedTemplateId = this._selectedTemplateId()
    return selectedTemplateId
      ? this._corporateTemplates().find((template) => template.id === selectedTemplateId) || null
      : null
  })

  readonly visibleCorporateTemplates = computed(() =>
    this._corporateTemplates().slice(0, this.visibleTemplateCount()),
  )

  constructor() {
    void api
      .getTemplates()
      .then((res) => this.setCorporateTemplates(res.templates || []))
      .catch(() => this.setCorporateTemplates([]))
  }

  private setCorporateTemplates(templates: CorporateTemplate[]): void {
    const previousLength = this._corporateTemplates().length
    this._corporateTemplates.set(templates)
    // React: useEffect(() => setVisibleTemplateCount(3), [corporateTemplates.length])
    if (templates.length !== previousLength) this.visibleTemplateCount.set(3)
  }

  setSelectedTemplateId = (id: string | null): void => {
    this._selectedTemplateId.set(id)
  }

  setTemplateMenuOpen = (open: boolean | ((prev: boolean) => boolean)): void => {
    this._templateMenuOpen.update((prev) => (typeof open === 'function' ? open(prev) : open))
  }

  handleTemplateListScroll = (event: Event): void => {
    const list = event.currentTarget as HTMLElement
    const reachedEnd = list.scrollTop + list.clientHeight >= list.scrollHeight - 24
    if (reachedEnd) {
      this.visibleTemplateCount.update((count) => Math.min(count + 3, this._corporateTemplates().length))
    }
  }
}
