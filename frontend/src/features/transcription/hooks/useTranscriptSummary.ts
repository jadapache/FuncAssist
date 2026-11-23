import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  transcriptionApi,
  type SummaryStatus,
  type SummaryTemplateItem,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { DEFAULT_SUMMARY_TEMPLATE, generateTranscriptSummary } from '../utils/summary'
import type { ToastApi } from './useTranscriptionJobRunners'
import { useLatest } from './useLatest'

const EMPTY_MARKERS = ['no se detectaron diálogos', 'no se detectaron dialogos', 'sin texto registrado']

interface SummaryDeps {
  transcriptionId: string
  title: string
  record: TranscriptionResult | null
  setRecord: (record: TranscriptionResult) => void
  onRecordSaved: (record: TranscriptionResult) => void
  toast: ToastApi
  /** Summary status reported by a running job (overrides the stored one). */
  jobSummaryStatus?: SummaryStatus | null
}

export function useTranscriptSummary(deps: SummaryDeps) {
  const { record } = deps
  const depsRef = useLatest(deps)
  const [templates, setTemplates] = useState<SummaryTemplateItem[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  const storedTemplateId = record?.summary?.template_id

  useEffect(() => {
    let mounted = true
    void transcriptionApi.getSummaryTemplates('transcript_summary').then((items) => {
      if (!mounted || items.length === 0) return
      setTemplates(items)
      setSelectedTemplate((prev) => (prev && items.some((t) => t.id === prev) ? prev : storedTemplateId || items[0].id))
    })
    return () => {
      mounted = false
    }
  }, [storedTemplateId])

  useEffect(() => {
    if (storedTemplateId) setSelectedTemplate(storedTemplateId)
  }, [storedTemplateId])

  const generate = useCallback(
    async (templateOverride?: string) => {
      const { transcriptionId, title, record: current, toast } = depsRef.current
      const templateId = templateOverride?.trim() || selectedTemplate || templates[0]?.id || DEFAULT_SUMMARY_TEMPLATE
      setIsGenerating(true)
      try {
        const updated = await generateTranscriptSummary({
          transcriptionId,
          title,
          templateId,
          templateTitle: templates.find((t) => t.id === templateId)?.title,
          record: current,
        })
        depsRef.current.setRecord(updated)
        depsRef.current.onRecordSaved(updated)
        toast.success('Resumen generado con éxito.')
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error desconocido.', 'Error al generar el resumen')
      } finally {
        setIsGenerating(false)
      }
    },
    [depsRef, selectedTemplate, templates],
  )

  const derived = useMemo(() => {
    const summary = record?.summary
    const paragraphs: string[] = []
    if (summary?.summary_text) {
      paragraphs.push(
        ...summary.summary_text
          .split('\n\n')
          .map((p) => p.trim())
          .filter(Boolean),
      )
    } else if (summary?.topics?.length) {
      paragraphs.push(
        `Durante la reunión se abordaron los aspectos principales vinculados a ${summary.topics.join(', ')}.`,
      )
      if (summary.decisions?.length) {
        paragraphs.push(`Como parte de los acuerdos alcanzados, se definió: ${summary.decisions.join('. ')}.`)
      }
    }
    const keyInsights =
      (summary?.key_insights?.length && summary.key_insights) ||
      (summary?.action_items?.length && summary.action_items) ||
      (summary?.requirements?.length && summary.requirements) ||
      []
    const hasTranscript = Boolean(record?.text?.trim() || record?.segments?.length)
    const hasRealParagraph = paragraphs.some(
      (p) => p && !EMPTY_MARKERS.some((marker) => p.toLowerCase().includes(marker)),
    )
    return {
      summaryText: summary?.summary_text || null,
      summaryParagraphs: paragraphs,
      keyInsights,
      hasTranscriptContent: hasTranscript,
      isSummaryReady: hasTranscript && (hasRealParagraph || keyInsights.length > 0),
    }
  }, [record])

  const summaryStatus: SummaryStatus | null = isGenerating
    ? 'running'
    : deps.jobSummaryStatus ?? record?.summary_status ?? null

  return {
    templates,
    selectedTemplate,
    setSelectedTemplate,
    isGenerating,
    summaryStatus,
    generate,
    ...derived,
  }
}
