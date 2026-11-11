import { useEffect, useState, type UIEvent } from 'react'
import { api, type CorporateTemplate } from '../../../api/client'

export function useCorporateTemplatesList() {
  const [corporateTemplates, setCorporateTemplates] = useState<CorporateTemplate[]>([])
  const [visibleTemplateCount, setVisibleTemplateCount] = useState(3)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const [templateMenuOpen, setTemplateMenuOpen] = useState(false)

  useEffect(() => {
    void api.getTemplates()
      .then((res) => setCorporateTemplates(res.templates || []))
      .catch(() => setCorporateTemplates([]))
  }, [])

  useEffect(() => {
    setVisibleTemplateCount(3)
  }, [corporateTemplates.length])

  const handleTemplateListScroll = (event: UIEvent<HTMLDivElement>) => {
    const list = event.currentTarget
    const reachedEnd = list.scrollTop + list.clientHeight >= list.scrollHeight - 24
    if (reachedEnd) {
      setVisibleTemplateCount((count) => Math.min(count + 3, corporateTemplates.length))
    }
  }

  const selectedTemplate = selectedTemplateId
    ? corporateTemplates.find((template) => template.id === selectedTemplateId) || null
    : null

  const visibleCorporateTemplates = corporateTemplates.slice(0, visibleTemplateCount)

  return {
    corporateTemplates,
    visibleCorporateTemplates,
    selectedTemplate,
    selectedTemplateId,
    setSelectedTemplateId,
    templateMenuOpen,
    setTemplateMenuOpen,
    handleTemplateListScroll,
  }
}
