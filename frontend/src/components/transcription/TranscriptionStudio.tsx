import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  ArrowLeft,
  Sparkles,
  Clock,
  Users,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Copy,
  Check,
  BookOpen,
  Volume2,
  Download,
  Star,
  FileText,
  ChevronDown,
} from 'lucide-react'
import {
  transcriptionApi,
  type TranscriptionResult,
  type TranscriptionProgress,
} from '../../api/modules/transcription'
import { useToast } from '../../context/ToastContext'
import { GenerateModal } from './GenerateModal'

interface TranscriptionStudioProps {
  transcriptionId: string
  activeProgress?: TranscriptionProgress | null
  onBackToDashboard: () => void
  onRefreshData?: () => void
}

function formatDuration(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs < 10 ? '0' : ''}${secs}`
}

function formatTimestamp(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`
}

// Generate consistent speaker badge color
const SPEAKER_COLORS = [
  'bg-blue-50 text-blue-700 border-blue-200',
  'bg-emerald-50 text-emerald-700 border-emerald-200',
  'bg-purple-50 text-purple-700 border-purple-200',
  'bg-amber-50 text-amber-800 border-amber-200',
  'bg-rose-50 text-rose-700 border-rose-200',
  'bg-cyan-50 text-cyan-700 border-cyan-200',
]

function getSpeakerColor(speakerName: string): string {
  let hash = 0
  for (let i = 0; i < speakerName.length; i++) {
    hash = speakerName.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % SPEAKER_COLORS.length
  return SPEAKER_COLORS[index]
}

function downloadFile(content: string, filename: string, mimeType: string) {
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

export const TranscriptionStudio: React.FC<TranscriptionStudioProps> = ({
  transcriptionId,
  activeProgress,
  onBackToDashboard,
  onRefreshData,
}) => {
  const { toast } = useToast()

  // State
  const [transcriptionResult, setTranscriptionResult] = useState<TranscriptionResult | null>(null)
  const [importantSegments, setImportantSegments] = useState<Set<number>>(new Set())
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const [isSavingKB, setIsSavingKB] = useState(false)
  const [hasCopiedTranscript, setHasCopiedTranscript] = useState(false)
  const [hasCopiedSummary, setHasCopiedSummary] = useState(false)
  const [generateModalOpen, setGenerateModalOpen] = useState(false)

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
  const toggleSegmentImportance = (index: number) => {
    setImportantSegments((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  // Handle AI summary generation
  const handleGenerateSummary = async () => {
    try {
      setIsGeneratingSummary(true)
      const res = await transcriptionApi.generateSummary(transcriptionId)
      if (res.transcription) {
        setTranscriptionResult(res.transcription)
        toast.success('¡Resumen ejecutivo generado con éxito!')
        onRefreshData?.()
      }
    } catch (err: any) {
      toast.error(`Error al generar resumen: ${err.message}`)
    } finally {
      setIsGeneratingSummary(false)
    }
  }

  // Save to Knowledge Base
  const handleSaveToKB = async () => {
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
  }

  // Rename speakers
  const handleSaveSpeakerNames = async () => {
    try {
      const res = await transcriptionApi.renameSpeakers(transcriptionId, speakerMap)
      setTranscriptionResult(res.transcription)
      setShowRenameModal(false)
      toast.success('Interlocutores actualizados.')
    } catch (err: any) {
      toast.error(`Error al renombrar: ${err.message}`)
    }
  }

  // 1. Copy transcript
  const handleCopyTranscript = () => {
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
  }

  // 2. Download transcript as TXT (Important in bold)
  const handleDownloadTranscriptTxt = () => {
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
  }

  // 3. Download transcript as JSON
  const handleDownloadTranscriptJson = () => {
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
  }

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

  // 4. Copy summary text
  const handleCopySummary = () => {
    if (!isSummaryReady) return
    let text = `# Summary\n\n${summaryParagraphs.join('\n\n')}\n\n# Key Insights\n\n`
    text += keyInsights.map((ki) => `• ${ki}`).join('\n\n')

    navigator.clipboard.writeText(text)
    setHasCopiedSummary(true)
    setTimeout(() => setHasCopiedSummary(false), 2000)
    toast.success('Resumen copiado al portapapeles.')
  }

  // 5. Download summary as TXT
  const handleDownloadSummaryTxt = () => {
    if (!transcriptionResult || !isSummaryReady) return
    const title = transcriptionResult.metadata?.title || 'Resumen'
    const safeTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_')

    let content = `Summary\n\n`
    content += `${summaryParagraphs.join('\n\n')}\n\n`
    content += `Key Insights\n\n`
    content += keyInsights.map((ki) => `• ${ki}`).join('\n\n')

    downloadFile(content, `Resumen_${safeTitle}.txt`, 'text/plain;charset=utf-8')
    setShowSummaryDownloadMenu(false)
  }

  // 6. Download summary as JSON
  const handleDownloadSummaryJson = () => {
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
  }

  const meetingTitle = transcriptionResult?.metadata?.title || activeProgress?.message || 'Transcripción de Reunión'

  return (
    <div className="flex flex-col h-[calc(100vh-5.5rem)] max-w-[1700px] mx-auto bg-slate-100 font-sans rounded-2xl border border-slate-300/80 shadow-md overflow-hidden animate-fade-in">
      {/* Top Workspace Header */}
      <header className="px-5 py-3 bg-white border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 shrink-0 shadow-2xs">
        <div className="flex items-center gap-3.5 min-w-0">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition flex items-center gap-1.5 text-xs font-bold cursor-pointer"
            title="Volver al panel de transcripciones"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Panel</span>
          </button>

          <div className="h-5 w-px bg-slate-200" />

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm sm:text-base font-bold text-slate-900 truncate" title={meetingTitle}>
                {meetingTitle}
              </h1>
              {activeProgress && isJobActive ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 animate-pulse">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>En vivo ({activeProgress.progress}%)</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>Completado</span>
                </span>
              )}
            </div>

            {transcriptionResult && (
              <div className="flex items-center gap-2.5 text-[11px] text-slate-500 mt-0.5">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3 text-slate-400" />
                  <span>{formatDuration(transcriptionResult.duration_seconds)} min</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3 text-slate-400" />
                  <span>{transcriptionResult.segments?.length || 0} turnos de voz</span>
                </span>
                <span>•</span>
                <span className="uppercase font-semibold text-slate-600">
                  Idioma: {transcriptionResult.language || 'ES'}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Top Header Actions */}
        <div className="flex items-center gap-2">
          {transcriptionResult && (
            <>
              {/* Guardar en Base de Conocimiento */}
              <button
                type="button"
                onClick={handleSaveToKB}
                disabled={isSavingKB || transcriptionResult.saved_to_knowledge}
                className={`px-3 py-1.5 text-xs font-semibold rounded-xl border transition flex items-center gap-1.5 shadow-2xs cursor-pointer ${
                  transcriptionResult.saved_to_knowledge
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
                }`}
                title="Guardar en biblioteca de conocimiento para consultas del agente"
              >
                <BookOpen className="h-3.5 w-3.5 text-[#002777]" />
                <span className="hidden md:inline">
                  {transcriptionResult.saved_to_knowledge ? 'En Base de Conocimiento' : 'Guardar en BC'}
                </span>
              </button>

              {/* Generar Documentos Button (Movido a la cabecera superior) */}
              <button
                type="button"
                onClick={() => setGenerateModalOpen(true)}
                disabled={!isSummaryReady || isJobActive}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition shadow-2xs cursor-pointer ${
                  isSummaryReady && !isJobActive
                    ? 'bg-[#002777] hover:bg-[#001e5c] text-white'
                    : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60'
                }`}
                title={
                  !isSummaryReady
                    ? 'Genera el resumen para habilitar la creación de entregables'
                    : 'Generar Inventario (.xlsx) y Levantamiento (.docx)'
                }
              >
                <Sparkles className={`h-3.5 w-3.5 ${isSummaryReady && !isJobActive ? 'text-amber-300' : 'text-slate-400'}`} />
                <span>Generar</span>
              </button>
            </>
          )}
        </div>
      </header>

      {/* Main Dual-Panel Workspace */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 bg-slate-100 overflow-hidden divide-y lg:divide-y-0 lg:divide-x divide-slate-300">
        {/* Left Panel: Transcripción */}
        <section className="flex-1 flex flex-col min-h-0 bg-white overflow-hidden">
          {/* Panel Header Toolbar */}
          <div className="h-11 px-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between shrink-0 shadow-2xs">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-blue-100 text-[#002777]">
                <Volume2 className="h-3.5 w-3.5" />
              </div>
              <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                Transcripción
              </h2>
            </div>

            {/* Action Buttons: Renombrar interlocutores, Copiar, Descargar (JSON, TXT) */}
            <div className="flex items-center gap-2">
              {/* Renombrar interlocutores (Icono grupo de personas) */}
              <button
                type="button"
                onClick={() => setShowRenameModal(true)}
                className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
                title="Renombrar interlocutores"
              >
                <Users className="h-3.5 w-3.5 text-[#002777]" />
              </button>

              <button
                type="button"
                onClick={handleCopyTranscript}
                disabled={!transcriptionResult?.segments?.length && !transcriptionResult?.text}
                className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
                title={hasCopiedTranscript ? 'Copiado al portapapeles' : 'Copiar texto de la transcripción'}
              >
                {hasCopiedTranscript ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                ) : (
                  <Copy className="h-3.5 w-3.5 text-slate-500" />
                )}
              </button>

              {/* Download Dropdown */}
              <div className="relative" ref={transcriptMenuRef}>
                <button
                  type="button"
                  onClick={() => setShowTranscriptDownloadMenu((prev) => !prev)}
                  disabled={!transcriptionResult?.segments?.length && !transcriptionResult?.text}
                  className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center gap-0.5"
                  title="Descargar transcripción"
                >
                  <Download className="h-3.5 w-3.5 text-slate-500" />
                  <ChevronDown className="h-3 w-3 text-slate-400" />
                </button>

                {showTranscriptDownloadMenu && (
                  <div className="absolute right-0 top-full mt-1.5 w-44 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-30 animate-scale-in">
                    <button
                      type="button"
                      onClick={handleDownloadTranscriptTxt}
                      className="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-[#002777] flex items-center gap-2 transition cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5 text-blue-600" />
                      <div>
                        <div className="font-bold">Texto (.txt)</div>
                        <div className="text-[10px] text-slate-400">Importantes en negrilla</div>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={handleDownloadTranscriptJson}
                      className="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-[#002777] flex items-center gap-2 transition cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5 text-amber-600" />
                      <div>
                        <div className="font-bold">Estructurado (.json)</div>
                        <div className="text-[10px] text-slate-400">Con metadatos y marcas</div>
                      </div>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Transcript Content List */}
          <div className="relative flex-1 min-h-0 overflow-y-auto p-5 sm:p-6 bg-white space-y-3">
            {/* Live Progress Pill if currently transcribing */}
            {activeProgress && isJobActive && (
              <div className="sticky top-0 z-20 mb-4 flex items-center gap-2 px-3.5 py-1.5 bg-slate-900/90 backdrop-blur-md text-white rounded-full shadow-lg border border-slate-700/60 text-xs animate-fade-in w-fit mx-auto">
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                </span>
                <span className="font-semibold text-slate-200">
                  {activeProgress.stage === 'preprocessing'
                    ? 'Extracción & separación de audio'
                    : activeProgress.stage === 'diarizing'
                    ? 'Diarización & separación de interlocutores'
                    : activeProgress.stage === 'summarizing'
                    ? 'Extracción de acuerdos & minutas'
                    : 'Inferencia acústica Whisper'}
                </span>
                <span className="text-slate-500">•</span>
                <span className="font-mono font-bold text-blue-400">
                  {activeProgress.progress}%
                </span>
              </div>
            )}

            {/* Empty state / Loading */}
            {!transcriptionResult?.segments?.length && !transcriptionResult?.text ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
                <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
                <p className="text-xs font-semibold text-slate-600">
                  {activeProgress?.message || 'Procesando transcripción de audio...'}
                </p>
                <p className="text-[11px] text-slate-400 max-w-xs">
                  Los segmentos y la identificación de interlocutores aparecerán aquí en tiempo real.
                </p>
              </div>
            ) : transcriptionResult.segments && transcriptionResult.segments.length > 0 ? (
              <div className="space-y-3 max-w-3xl">
                <p className="text-[11px] text-slate-400 italic mb-2">
                  * Haz clic en cualquier segmento para marcarlo o desmarcarlo como <strong>importante</strong>.
                </p>

                {transcriptionResult.segments.map((seg, idx) => {
                  const isImportant = importantSegments.has(idx)
                  const speakerColorClass = getSpeakerColor(seg.speaker || 'Participante')

                  return (
                    <div
                      key={idx}
                      onClick={() => toggleSegmentImportance(idx)}
                      className={`group relative p-3.5 rounded-2xl border transition-all duration-150 cursor-pointer ${
                        isImportant
                          ? 'bg-amber-50/70 border-amber-300 ring-1 ring-amber-200/80 shadow-xs'
                          : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 shadow-2xs'
                      }`}
                    >
                      {/* Segment Header */}
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2.5 py-0.5 rounded-lg text-xs font-bold border shadow-2xs ${speakerColorClass}`}
                          >
                            {seg.speaker || 'Participante'}
                          </span>
                          <span className="text-[11px] font-mono font-medium text-slate-400">
                            [{formatTimestamp(seg.start)}]
                          </span>
                        </div>

                        {/* Star / Bookmark Icon */}
                        <div className="flex items-center gap-1.5">
                          {isImportant && (
                            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-800 bg-amber-100 px-2 py-0.5 rounded-md">
                              Importante
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleSegmentImportance(idx)
                            }}
                            className={`p-1 rounded-lg transition ${
                              isImportant
                                ? 'text-amber-500 hover:text-amber-600'
                                : 'text-slate-300 group-hover:text-slate-400 hover:text-amber-500'
                            }`}
                            title={isImportant ? 'Desmarcar de importante' : 'Marcar como importante'}
                          >
                            <Star className={`h-4 w-4 ${isImportant ? 'fill-amber-400 text-amber-500' : ''}`} />
                          </button>
                        </div>
                      </div>

                      {/* Dialogue text */}
                      <p
                        className={`text-sm leading-relaxed ${
                          isImportant ? 'font-semibold text-slate-900' : 'text-slate-700'
                        }`}
                      >
                        {seg.text}
                      </p>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
                {transcriptionResult.text}
              </div>
            )}
          </div>
        </section>

        {/* Right Panel: Resumen */}
        <aside className="w-full lg:w-[480px] xl:w-[540px] flex flex-col min-h-0 bg-white shrink-0">
          {/* Panel Header Toolbar */}
          <div className="h-11 px-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between shrink-0 shadow-2xs">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-100 text-amber-800">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                Resumen
              </h2>
            </div>

            {/* Action Buttons: Copiar, Descargar, Regenerar */}
            <div className="flex items-center gap-2">
              {/* Copy Summary Button */}
              <button
                type="button"
                onClick={handleCopySummary}
                disabled={!isSummaryReady}
                className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
                title={hasCopiedSummary ? 'Copiado al portapapeles' : 'Copiar resumen'}
              >
                {hasCopiedSummary ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                ) : (
                  <Copy className="h-3.5 w-3.5 text-slate-500" />
                )}
              </button>

              {/* Download Summary Dropdown */}
              <div className="relative" ref={summaryMenuRef}>
                <button
                  type="button"
                  onClick={() => setShowSummaryDownloadMenu((prev) => !prev)}
                  disabled={!isSummaryReady}
                  className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center gap-0.5"
                  title="Descargar resumen"
                >
                  <Download className="h-3.5 w-3.5 text-slate-500" />
                  <ChevronDown className="h-3 w-3 text-slate-400" />
                </button>

                {showSummaryDownloadMenu && (
                  <div className="absolute right-0 top-full mt-1.5 w-44 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-30 animate-scale-in">
                    <button
                      type="button"
                      onClick={handleDownloadSummaryTxt}
                      className="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-[#002777] flex items-center gap-2 transition cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5 text-blue-600" />
                      <div>
                        <div className="font-bold">Texto (.txt)</div>
                        <div className="text-[10px] text-slate-400">Formato lectura limpia</div>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={handleDownloadSummaryJson}
                      className="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-[#002777] flex items-center gap-2 transition cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5 text-amber-600" />
                      <div>
                        <div className="font-bold">Estructurado (.json)</div>
                        <div className="text-[10px] text-slate-400">Párrafos e insights</div>
                      </div>
                    </button>
                  </div>
                )}
              </div>

              {/* Regenerate Summary Button */}
              {isSummaryReady && (
                <button
                  type="button"
                  onClick={handleGenerateSummary}
                  disabled={isGeneratingSummary}
                  className="p-1.5 bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
                  title="Regenerar resumen con IA"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isGeneratingSummary ? 'animate-spin text-[#002777]' : ''}`} />
                </button>
              )}
            </div>
          </div>

          {/* Panel Body: Clean Reading View matching reference image */}
          <div className="flex-1 min-h-0 overflow-y-auto p-6 sm:p-8 bg-white space-y-6">
            {isGeneratingSummary ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
                <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
                <p className="text-xs font-semibold text-slate-700">
                  Generando resumen ejecutivo con IA...
                </p>
                <p className="text-[11px] text-slate-400 max-w-xs">
                  Extrayendo contexto, acuerdos clave y puntos destacados de la reunión.
                </p>
              </div>
            ) : isSummaryReady ? (
              <div className="space-y-6 animate-fade-in max-w-xl">
                {/* 1. Summary Section */}
                {summaryParagraphs.length > 0 && (
                  <section className="space-y-4">
                    <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                      Summary
                    </h2>
                    <div className="space-y-4 text-sm text-slate-700 leading-relaxed font-normal">
                      {summaryParagraphs.map((paragraph, idx) => (
                        <p key={idx} className="leading-relaxed">
                          {paragraph}
                        </p>
                      ))}
                    </div>
                  </section>
                )}

                {/* 2. Key Insights Section */}
                {keyInsights.length > 0 && (
                  <section className="space-y-3.5 pt-2">
                    <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                      Key Insights
                    </h3>
                    <ul className="space-y-3">
                      {keyInsights.map((insight, idx) => (
                        <li key={idx} className="flex items-start gap-3 text-sm text-slate-700 leading-relaxed">
                          <span className="h-1.5 w-1.5 rounded-full bg-slate-400 mt-2 shrink-0" />
                          <span>{insight}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-4 text-slate-400">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
                  <Sparkles className="h-6 w-6" />
                </div>
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-slate-800">
                    Resumen Ejecutivo no generado
                  </h4>
                  <p className="text-xs text-slate-500 max-w-xs">
                    Genera una síntesis ejecutiva con IA para extraer los puntos clave y habilitar los entregables funcionales.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleGenerateSummary}
                  disabled={isJobActive}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-[#002777] hover:bg-[#001e5c] text-white text-xs font-bold rounded-xl shadow-xs transition cursor-pointer disabled:opacity-40"
                >
                  <Sparkles className="h-3.5 w-3.5 text-amber-300" />
                  <span>Generar Resumen Ejecutivo</span>
                </button>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Speaker Rename Modal */}
      {showRenameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-fade-in">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Users className="h-4 w-4 text-[#002777]" />
                <span>Renombrar Interlocutores</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowRenameModal(false)}
                className="text-slate-400 hover:text-slate-600 text-xs cursor-pointer"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Asigna nombres reales a los identificadores detectados por el motor de diarización:
            </p>

            <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
              {Object.keys(speakerMap).map((spk) => (
                <div key={spk} className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-600 w-32 shrink-0 truncate">
                    {spk}:
                  </span>
                  <input
                    type="text"
                    value={speakerMap[spk]}
                    onChange={(e) =>
                      setSpeakerMap({
                        ...speakerMap,
                        [spk]: e.target.value,
                      })
                    }
                    className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777]"
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowRenameModal(false)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleSaveSpeakerNames}
                className="btn-primary px-4 py-1.5 text-xs rounded-xl font-bold cursor-pointer"
              >
                Guardar Nombres
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Generate Deliverables Modal */}
      <GenerateModal
        isOpen={generateModalOpen}
        transcriptionId={transcriptionId}
        meetingTitle={meetingTitle}
        onClose={() => setGenerateModalOpen(false)}
      />
    </div>
  )
}
