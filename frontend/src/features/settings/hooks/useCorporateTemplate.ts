import { useState, useEffect } from 'react'
import { api, type CorporateTemplate } from '../../../api/client'

export function useCorporateTemplate(moduleSlug: string, defaultFallback: string) {
  const [templateContent, setTemplateContent] = useState<string>(defaultFallback)
  const [activeTemplate, setActiveTemplate] = useState<CorporateTemplate | null>(null)
  const [loadingTemplate, setLoadingTemplate] = useState<boolean>(true)

  useEffect(() => {
    let isMounted = true

    async function fetchTemplate() {
      setLoadingTemplate(true)
      try {
        const res = await api.getTemplates()
        const templates = res.templates || []

        // Search for a template matching the module slug or fallback to first available
        const matched =
          templates.find((t) => t.module?.toLowerCase() === moduleSlug.toLowerCase()) ||
          templates[0]

        if (matched && isMounted) {
          setActiveTemplate(matched)
          const detail = await api.getTemplateContent(matched.id)
          if (detail.content && isMounted) {
            setTemplateContent(detail.content)
          }
        }
      } catch (err) {
        console.warn('Could not load corporate template from backend, using fallback:', err)
      } finally {
        if (isMounted) setLoadingTemplate(false)
      }
    }

    void fetchTemplate()

    return () => {
      isMounted = false
    }
  }, [moduleSlug])

  return { templateContent, activeTemplate, loadingTemplate }
}
