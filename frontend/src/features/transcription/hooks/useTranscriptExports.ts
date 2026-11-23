import { copyText } from '../../../core/browser/secureContext'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { TranscriptionResult } from '../api/transcriptionApi'
import { downloadTextFile, formatTranscriptForExport, safeFilename } from '../utils/transcriptFormat'
import { formatDuration } from '../utils/time'
import type { TextMode } from '../utils/turns'
import type { ToastApi } from './useTranscriptionJobRunners'

interface ExportDeps {
  record: TranscriptionResult | null
  textMode: TextMode
  summaryText: string | null
  summaryParagraphs: string[]
  keyInsights: string[]
  isSummaryReady: boolean
  toast: ToastApi
}

function useClickOutside(onOutside: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  const callbackRef = useRef(onOutside)
  callbackRef.current = onOutside
  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) callbackRef.current()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])
  return ref
}

function useCopiedFlag() {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])
  const flag = useCallback(() => {
    setCopied(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied(false), 2000)
  }, [])
  return [copied, flag] as const
}

/** Copy and download actions for the transcript and its summary. */
export function useTranscriptExports(deps: ExportDeps) {
  const { record, textMode, summaryText, summaryParagraphs, keyInsights, isSummaryReady, toast } = deps
  const [transcriptMenuOpen, setTranscriptMenuOpen] = useState(false)
  const [summaryMenuOpen, setSummaryMenuOpen] = useState(false)
  const transcriptMenuRef = useClickOutside(() => setTranscriptMenuOpen(false))
  const summaryMenuRef = useClickOutside(() => setSummaryMenuOpen(false))
  const [copiedTranscript, flagTranscriptCopied] = useCopiedFlag()
  const [copiedSummary, flagSummaryCopied] = useCopiedFlag()

  const title = record?.metadata?.title || 'Transcripción'

  const copyTranscript = useCallback(async () => {
    const content = formatTranscriptForExport(record, textMode, true)
    if (!content) return
    try {
      if (!(await copyText(content))) throw new Error('No se pudo copiar')
      flagTranscriptCopied()
      toast.success('Transcripción copiada al portapapeles.')
    } catch {
      toast.error('No se pudo copiar al portapapeles.')
    }
  }, [record, textMode, toast, flagTranscriptCopied])

  const downloadTranscriptTxt = useCallback(() => {
    if (!record) return
    const header = [
      `# Transcripción: ${title}`,
      `Fecha: ${record.created_at}`,
      `Duración: ${formatDuration(record.duration_seconds)}`,
      textMode === 'raw' ? 'Texto: literal' : 'Texto: limpio',
      '',
      '------------------------------------------------------------',
      '',
    ].join('\n')
    const body = formatTranscriptForExport(record, textMode) || 'Sin texto registrado.'
    downloadTextFile(`${header}\n${body}`, `Transcripcion_${safeFilename(title, 'Transcripcion')}.txt`, 'text/plain;charset=utf-8')
    setTranscriptMenuOpen(false)
  }, [record, textMode, title])

  const downloadTranscriptJson = useCallback(() => {
    if (!record) return
    downloadTextFile(
      JSON.stringify(record, null, 2),
      `Transcripcion_${safeFilename(title, 'Transcripcion')}.json`,
      'application/json;charset=utf-8',
    )
    setTranscriptMenuOpen(false)
  }, [record, title])

  const summaryMarkdown = useCallback(() => {
    if (summaryText) return summaryText
    let content = `# Resumen: ${title}\n\n`
    if (summaryParagraphs.length > 0) content += `## Puntos clave\n\n${summaryParagraphs.join('\n\n')}\n\n`
    if (keyInsights.length > 0) content += `## Insights principales\n\n${keyInsights.map((ki) => `- ${ki}`).join('\n')}\n`
    return content
  }, [summaryText, summaryParagraphs, keyInsights, title])

  const copySummary = useCallback(async () => {
    if (!isSummaryReady) return
    try {
      if (!(await copyText(summaryMarkdown()))) throw new Error('No se pudo copiar')
      flagSummaryCopied()
      toast.success('Resumen copiado al portapapeles.')
    } catch {
      toast.error('No se pudo copiar al portapapeles.')
    }
  }, [isSummaryReady, summaryMarkdown, toast, flagSummaryCopied])

  const downloadSummaryMd = useCallback(() => {
    if (!isSummaryReady) return
    downloadTextFile(summaryMarkdown(), `Resumen_${safeFilename(title, 'Resumen')}.md`, 'text/markdown;charset=utf-8')
    setSummaryMenuOpen(false)
  }, [isSummaryReady, summaryMarkdown, title])

  const downloadSummaryJson = useCallback(() => {
    if (!isSummaryReady) return
    const data = {
      meeting_title: title,
      summary_paragraphs: summaryParagraphs,
      key_insights: keyInsights,
      summary_raw: record?.summary ?? null,
    }
    downloadTextFile(JSON.stringify(data, null, 2), `Resumen_${safeFilename(title, 'Resumen')}.json`, 'application/json;charset=utf-8')
    setSummaryMenuOpen(false)
  }, [isSummaryReady, keyInsights, record, summaryParagraphs, title])

  return {
    transcriptMenuOpen,
    setTranscriptMenuOpen,
    summaryMenuOpen,
    setSummaryMenuOpen,
    transcriptMenuRef,
    summaryMenuRef,
    copiedTranscript,
    copiedSummary,
    copyTranscript,
    downloadTranscriptTxt,
    downloadTranscriptJson,
    copySummary,
    downloadSummaryMd,
    downloadSummaryJson,
  }
}
