/**
 * useTranscriptionActions.ts
 * Extracted actions and business logic for TranscriptionStudio
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  transcriptionApi,
  type TranscriptionResult,
  type TranscriptionProgress,
} from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'

export function formatDuration(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs < 10 ? '0' : ''}${secs}`
}

export function formatTimestamp(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`
}

export const SPEAKER_COLORS = [
  'bg-blue-50 text-blue-700 border-blue-200',
  'bg-emerald-50 text-emerald-700 border-emerald-200',
  'bg-purple-50 text-purple-700 border-purple-200',
  'bg-amber-50 text-amber-800 border-amber-200',
  'bg-rose-50 text-rose-700 border-rose-200',
  'bg-cyan-50 text-cyan-700 border-cyan-200',
]

export function getSpeakerColor(speakerName: string): string {
  let hash = 0
  for (let i = 0; i < speakerName.length; i++) {
    hash = speakerName.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % SPEAKER_COLORS.length
  return SPEAKER_COLORS[index]
}

export function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function useTranscriptionActions(
  transcriptionId: string,
  activeProgress?: TranscriptionProgress | null,
  onRefreshData?: () => void,
  initialMeetingTitle?: string,
  onRetranscribe?: (transcriptionId: string, title?: string) => Promise<void>,
) {
  const { toast } = useToast()

  // State
  const [transcriptionResult, setTranscriptionResult] = useState<TranscriptionResult | null>(null)
  const [importantSegments, setImportantSegments] = useState<Set<number>>(new Set())
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const [isSavingKB, setIsSavingKB] = useState(false)
  const [hasCopiedTranscript, setHasCopiedTranscript] = useState(false)
  const [hasCopiedSummary, setHasCopiedSummary] = useState(false)
  const [generateModalOpen, setGenerateModalOpen] = useState(false)

  const meetingTitle =
    transcriptionResult?.metadata?.title ||
    activeProgress?.title ||
    initialMeetingTitle ||
    'Transcripción de Reunión'

  // Download dropdown toggles
  const [showTranscriptDownloadMenu, setShowTranscriptDownloadMenu] = useState(false)
  const [showSummaryDownloadMenu, setShowSummaryDownloadMenu] = useState(false)

  // Speaker rename state
  const [showRenameModal, setShowRenameModal] = useState(false)
  const [speakerMap, setSpeakerMap] = useState<Record<string, string>>({})

  // Dropdown dismiss refs
  const transcriptMenuRef = useRef<HTMLDivElement>(null)
  const summaryMenuRef = useRef<HTMLDivElement>(null)

  // Job active status
  const isJobActive = Boolean(
    activeProgress && activeProgress.status !== 'complete' && activeProgress.status !== 'failed'
  )

  // Fetch transcription data
  const loadTranscription = useCallback(async () => {
    try {
      const res = await transcriptionApi.getTranscriptionResult(transcriptionId)
      setTranscriptionResult(res)

      // Initialize unique speakers map
      const speakers = Array.from(new Set(res.segments?.map((s) => s.speaker) || []))
      const initMap: Record<string, string> = {}
      speakers.forEach((spk) => {
        initMap[spk] = spk
      })
      setSpeakerMap(initMap)
    } catch (err: any) {
      console.warn('Could not load transcription result:', err)
    }
  }, [transcriptionId])

  useEffect(() => {
    loadTranscription()
  }, [loadTranscription])

  // Reload when job finishes
  useEffect(() => {
    if (activeProgress && activeProgress.status === 'complete') {
      loadTranscription()
      onRefreshData?.()
    }
  }, [activeProgress?.status, loadTranscription, onRefreshData])

  // Close menus on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (transcriptMenuRef.current && !transcriptMenuRef.current.contains(e.target as Node)) {
        setShowTranscriptDownloadMenu(false)
      }
      if (summaryMenuRef.current && !summaryMenuRef.current.contains(e.target as Node)) {
        setShowSummaryDownloadMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Toggle segment importance
  const toggleSegmentImportance = useCallback((index: number) => {
    setImportantSegments((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }, [])

  const [isRetranscribing, setIsRetranscribing] = useState(false)

  // Handle re-transcription / regeneration with current configured model
  const handleRetranscribe = useCallback(async () => {
    try {
      setIsRetranscribing(true)
      if (onRetranscribe) {
        await onRetranscribe(transcriptionId, meetingTitle)
      } else {
        await transcriptionApi.retranscribe(transcriptionId, {
          mode: 'auto',
          enable_diarization: true,
        })
        toast.info('Regeneración de transcripción iniciada.')
        onRefreshData?.()
      }
    } catch (err: any) {
      toast.error(`Error al regenerar transcripción: ${err.message}`)
    } finally {
      setIsRetranscribing(false)
    }
  }, [transcriptionId, meetingTitle, onRetranscribe, toast, onRefreshData])

  // Handle AI summary generation
  const handleGenerateSummary = useCallback(async () => {
    try {
      setIsGeneratingSummary(true)
      const res = await transcriptionApi.generateSummary(transcriptionId)
      if (res.transcription) {
        setTranscriptionResult(res.transcription)
        toast.success('¡Resumen generado con éxito!')
        onRefreshData?.()
      }
    } catch (err: any) {
      toast.error(`Error al generar resumen: ${err.message}`)
    } finally {
      setIsGeneratingSummary(false)
    }
  }, [transcriptionId, toast, onRefreshData])

  // Save to Knowledge Base
  const handleSaveToKB = useCallback(async () => {
    try {
      setIsSavingKB(true)
      await transcriptionApi.saveToKnowledgeBase(transcriptionId, ['reunion', 'transcripcion'])
      toast.success('Transcripción y resumen indexados en la Base de Conocimiento.')
      if (transcriptionResult) {
        setTranscriptionResult({ ...transcriptionResult, saved_to_knowledge: true })
      }
    } catch (err: any) {
      toast.error(`Error al guardar en Base de Conocimiento: ${err.message}`)
    } finally {
      setIsSavingKB(false)
    }
  }, [transcriptionId, transcriptionResult, toast])

  // Rename speakers
  const handleSaveSpeakerNames = useCallback(async () => {
    try {
      const res = await transcriptionApi.renameSpeakers(transcriptionId, speakerMap)
      setTranscriptionResult(res.transcription)
      setShowRenameModal(false)
      toast.success('Interlocutores actualizados.')
    } catch (err: any) {
      toast.error(`Error al renombrar: ${err.message}`)
    }
  }, [transcriptionId, speakerMap, toast])

  // Copy transcript
  const handleCopyTranscript = useCallback(() => {
    if (!transcriptionResult?.segments || transcriptionResult.segments.length === 0) {
      if (transcriptionResult?.text) {
        navigator.clipboard.writeText(transcriptionResult.text)
        setHasCopiedTranscript(true)
        setTimeout(() => setHasCopiedTranscript(false), 2000)
        toast.success('Transcripción copiada.')
      }
      return
    }

    const lines = transcriptionResult.segments.map((seg, idx) => {
      const time = formatTimestamp(seg.start)
      const isImportant = importantSegments.has(idx)
      const prefix = isImportant ? '**[IMPORTANTE] ' : ''
      const suffix = isImportant ? '**' : ''
      return `${prefix}[${time}] ${seg.speaker}: ${seg.text}${suffix}`
    })

    navigator.clipboard.writeText(lines.join('\n\n'))
    setHasCopiedTranscript(true)
    setTimeout(() => setHasCopiedTranscript(false), 2000)
    toast.success('Transcripción copiada al portapapeles.')
  }, [transcriptionResult, importantSegments, toast])

  // Download transcript as TXT
  const handleDownloadTranscriptTxt = useCallback(() => {
    if (!transcriptionResult) return
    const title = transcriptionResult.metadata?.title || 'Transcripcion'
    const safeTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_')

    let content = `# Transcripción: ${title}\n`
    content += `Fecha: ${transcriptionResult.created_at}\n`
    content += `Duración: ${Math.round(transcriptionResult.duration_seconds)} segundos\n\n`
    content += `------------------------------------------------------------\n\n`

    if (transcriptionResult.segments && transcriptionResult.segments.length > 0) {
      const lines = transcriptionResult.segments.map((seg, idx) => {
        const time = formatTimestamp(seg.start)
        const isImportant = importantSegments.has(idx)
        if (isImportant) {
          return `**[${time}] ${seg.speaker}: ${seg.text}**`
        }
        return `[${time}] ${seg.speaker}: ${seg.text}`
      })
      content += lines.join('\n\n')
    } else {
      content += transcriptionResult.text || 'Sin texto registrado.'
    }

    downloadFile(content, `Transcripcion_${safeTitle}.txt`, 'text/plain;charset=utf-8')
    setShowTranscriptDownloadMenu(false)
  }, [transcriptionResult, importantSegments])

  // Download transcript as JSON
  const handleDownloadTranscriptJson = useCallback(() => {
    if (!transcriptionResult) return
    const safeTitle = (transcriptionResult.metadata?.title || 'Transcripcion').replace(/[^a-zA-Z0-9_-]/g, '_')

    const data = {
      ...transcriptionResult,
      segments: transcriptionResult.segments.map((s, idx) => ({
        ...s,
        is_important: importantSegments.has(idx),
      })),
    }

    downloadFile(JSON.stringify(data, null, 2), `Transcripcion_${safeTitle}.json`, 'application/json;charset=utf-8')
    setShowTranscriptDownloadMenu(false)
  }, [transcriptionResult, importantSegments])

  // Extract Summary paragraphs and key insights cleanly
  const summaryData = transcriptionResult?.summary
  const summaryParagraphs: string[] = []

  if (summaryData?.summary_text) {
    summaryParagraphs.push(
      ...summaryData.summary_text
        .split('\n\n')
        .map((p) => p.trim())
        .filter(Boolean)
    )
  } else if (summaryData?.topics && summaryData.topics.length > 0) {
    summaryParagraphs.push(
      `Durante la reunión se abordaron los aspectos principales vinculados a ${summaryData.topics.join(
        ', '
      )}. Los participantes evaluaron los requerimientos y el alcance operativo para la solución requerida.`
    )
    if (summaryData.decisions && summaryData.decisions.length > 0) {
      summaryParagraphs.push(
        `Como parte de los acuerdos alcanzados, se definió: ${summaryData.decisions.join('. ')}.`
      )
    }
  }

  const keyInsights: string[] =
    summaryData?.key_insights && summaryData.key_insights.length > 0
      ? summaryData.key_insights
      : summaryData?.action_items && summaryData.action_items.length > 0
        ? summaryData.action_items
        : summaryData?.requirements && summaryData.requirements.length > 0
          ? summaryData.requirements
          : []

  const isSummaryReady = summaryParagraphs.length > 0 || keyInsights.length > 0

  // Copy summary text
  const handleCopySummary = useCallback(() => {
    if (!isSummaryReady) return
    let text = `# Summary\n\n${summaryParagraphs.join('\n\n')}\n\n# Key Insights\n\n`
    text += keyInsights.map((ki) => `• ${ki}`).join('\n\n')

    navigator.clipboard.writeText(text)
    setHasCopiedSummary(true)
    setTimeout(() => setHasCopiedSummary(false), 2000)
    toast.success('Resumen copiado al portapapeles.')
  }, [isSummaryReady, summaryParagraphs, keyInsights, toast])

  // Download summary as TXT
  const handleDownloadSummaryTxt = useCallback(() => {
    if (!transcriptionResult || !isSummaryReady) return
    const title = transcriptionResult.metadata?.title || 'Resumen'
    const safeTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_')

    let content = `Summary\n\n`
    content += `${summaryParagraphs.join('\n\n')}\n\n`
    content += `Key Insights\n\n`
    content += keyInsights.map((ki) => `• ${ki}`).join('\n\n')

    downloadFile(content, `Resumen_${safeTitle}.txt`, 'text/plain;charset=utf-8')
    setShowSummaryDownloadMenu(false)
  }, [transcriptionResult, isSummaryReady, summaryParagraphs, keyInsights])

  // Download summary as JSON
  const handleDownloadSummaryJson = useCallback(() => {
    if (!transcriptionResult || !isSummaryReady) return
    const safeTitle = (transcriptionResult.metadata?.title || 'Resumen').replace(/[^a-zA-Z0-9_-]/g, '_')

    const data = {
      meeting_title: transcriptionResult.metadata?.title,
      summary_paragraphs: summaryParagraphs,
      key_insights: keyInsights,
      summary_raw: summaryData,
    }

    downloadFile(JSON.stringify(data, null, 2), `Resumen_${safeTitle}.json`, 'application/json;charset=utf-8')
    setShowSummaryDownloadMenu(false)
  }, [transcriptionResult, isSummaryReady, summaryParagraphs, keyInsights, summaryData])

  return {
    transcriptionResult,
    importantSegments,
    isGeneratingSummary,
    isSavingKB,
    hasCopiedTranscript,
    hasCopiedSummary,
    generateModalOpen,
    setGenerateModalOpen,
    showTranscriptDownloadMenu,
    setShowTranscriptDownloadMenu,
    showSummaryDownloadMenu,
    setShowSummaryDownloadMenu,
    showRenameModal,
    setShowRenameModal,
    speakerMap,
    setSpeakerMap,
    transcriptMenuRef,
    summaryMenuRef,
    isJobActive,
    summaryParagraphs,
    keyInsights,
    isSummaryReady,
    meetingTitle,
    isRetranscribing,
    toggleSegmentImportance,
    handleRetranscribe,
    handleGenerateSummary,
    handleSaveToKB,
    handleSaveSpeakerNames,
    handleCopyTranscript,
    handleDownloadTranscriptTxt,
    handleDownloadTranscriptJson,
    handleCopySummary,
    handleDownloadSummaryTxt,
    handleDownloadSummaryJson,
  }
}
