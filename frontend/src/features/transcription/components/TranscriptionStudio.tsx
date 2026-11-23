import React, { useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  BookOpen,
  CheckCircle2,
  Clock,
  Loader2,
  Sparkles,
  Users,
} from 'lucide-react'
import { transcriptionApi, type TranscriptionResult, type TranscriptionStage } from '../api/transcriptionApi'
import type { TranscriptionJob } from '../context/transcriptionJobs'
import { useToast } from '../../../context/ToastContext'
import { useTranscriptionRecord } from '../hooks/useTranscriptionRecord'
import { useSpeakerEditing } from '../hooks/useSpeakerEditing'
import { useTranscriptSummary } from '../hooks/useTranscriptSummary'
import { useTranscriptExports } from '../hooks/useTranscriptExports'
import { formatDuration } from '../utils/time'
import { getStageText, isTerminalStage, normalizeStage } from '../utils/transcriptionStages'
import type { TextMode } from '../utils/turns'
import { GenerateModal } from './GenerateModal'
import { TranscriptionViewer } from './TranscriptionViewer'
import { SummaryPanel } from './SummaryPanel'
import { SpeakerManager } from './SpeakerManager'
import { SegmentEditModal } from './SegmentEditModal'

interface TranscriptionStudioProps {
  transcriptionId: string
  initialMeetingTitle?: string
  /** Job of this transcription in the store (running, failed or just finished), if any. */
  job: TranscriptionJob | null
  onBackToDashboard: () => void
  onRegenerate: (record: TranscriptionResult) => Promise<void>
  onRetry: (transcriptionId: string, title?: string) => Promise<void>
  onCancel: (transcriptionId: string) => Promise<void>
  onRequestReupload: () => void
  onRecordSaved: (record: TranscriptionResult) => void
}

const PROBLEM_STAGES: ReadonlySet<TranscriptionStage> = new Set(['failed', 'interrupted', 'cancelled'])

/** Older records may lack `has_media`: browser transcriptions never stored the media. */
function recordHasMedia(record: TranscriptionResult): boolean {
  if (typeof record.has_media === 'boolean') return record.has_media
  if (record.source) return record.source === 'cloud'
  return !String(record.model_info || '').toLowerCase().includes('client')
}

export const TranscriptionStudio: React.FC<TranscriptionStudioProps> = ({
  transcriptionId,
  initialMeetingTitle,
  job,
  onBackToDashboard,
  onRegenerate,
  onRetry: _onRetry,
  onCancel: _onCancel,
  onRequestReupload,
  onRecordSaved,
}) => {
  const { toast } = useToast()
  const { record, setRecord, loadState, loadError, reload } = useTranscriptionRecord(transcriptionId, job)
  const [textMode, setTextMode] = useState<TextMode>('clean')
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null)
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [isSavingKB, setIsSavingKB] = useState(false)

  const jobRunning = Boolean(job && !isTerminalStage(job.stage))
  const meetingTitle = record?.metadata?.title || job?.title || initialMeetingTitle || 'Transcripción de reunión'

  const speakerEditing = useSpeakerEditing({ record, setRecord, onRecordSaved, toast, disabled: jobRunning })
  const summary = useTranscriptSummary({
    transcriptionId,
    title: meetingTitle,
    record,
    setRecord,
    onRecordSaved,
    toast,
    jobSummaryStatus: job?.summary_status,
  })
  const exports = useTranscriptExports({
    record,
    textMode,
    summaryText: summary.summaryText,
    summaryParagraphs: summary.summaryParagraphs,
    keyInsights: summary.keyInsights,
    isSummaryReady: summary.isSummaryReady,
    toast,
  })

  // A browser job shows its segments as they arrive; otherwise the saved record is shown.
  const showLiveSegments = Boolean(
    job && job.kind === 'browser' && !record?.segments?.length && (jobRunning || job.liveSegments.length > 0),
  )
  const segments = useMemo(
    () => (showLiveSegments && job ? job.liveSegments : record?.segments ?? []),
    [showLiveSegments, job, record],
  )
  const hasRawText = useMemo(
    () => segments.some((segment) => Boolean(segment.text_raw) && segment.text_raw?.trim() !== segment.text.trim()),
    [segments],
  )

  // Status: the job when there is one, otherwise the stored record.
  const recordStage = record?.status ? normalizeStage(record.status) : null
  const statusStage: TranscriptionStage | null = job
    ? normalizeStage(job.stage)
    : recordStage && PROBLEM_STAGES.has(recordStage)
      ? recordStage
      : null
  const hasMedia = record ? recordHasMedia(record) : job?.kind === 'server'

  const regenerateMode: 'server' | 'reupload' | null = record ? (hasMedia ? 'server' : 'reupload') : null
  const editingSegment = editingSegmentId ? record?.segments.find((segment) => segment.id === editingSegmentId) : undefined
  const speakersCount = speakerEditing.speakers.length

  const handleRegenerate = async () => {
    if (!record) return
    if (regenerateMode === 'reupload') {
      onRequestReupload()
      return
    }
    setIsRegenerating(true)
    try {
      await onRegenerate(record)
    } finally {
      setIsRegenerating(false)
    }
  }

  const handleSaveToKB = async () => {
    try {
      setIsSavingKB(true)
      await transcriptionApi.saveToKnowledgeBase(transcriptionId, ['reunion', 'transcripcion'])
      toast.success('Transcripción y resumen indexados en la Base de Conocimiento.')
      if (record) {
        const updated = { ...record, saved_to_knowledge: true }
        setRecord(updated)
        onRecordSaved(updated)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar', 'Error al guardar en Base de Conocimiento')
    } finally {
      setIsSavingKB(false)
    }
  }

  const renderStatusBadge = () => {
    if (jobRunning && job) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-50 text-[#002777] border border-blue-200/80 shadow-2xs">
          <Loader2 className="h-3 w-3 animate-spin text-[#002777]" />
          <span>En curso ({job.progress}%)</span>
        </span>
      )
    }
    if (statusStage === 'failed' || statusStage === 'interrupted') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-red-100 text-red-800">
          <AlertTriangle className="h-3 w-3" />
          <span>{statusStage === 'interrupted' ? 'Interrumpida' : 'Error'}</span>
        </span>
      )
    }
    if (statusStage === 'cancelled') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700">
          <Ban className="h-3 w-3" />
          <span>Cancelada</span>
        </span>
      )
    }
    if (!record) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-600">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Cargando</span>
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
        <CheckCircle2 className="h-3 w-3" />
        <span>Completado</span>
      </span>
    )
  }

  const renderBody = () => {
    if (!record && !jobRunning && !job) {
      if (loadState === 'loading') {
        return (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-white text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
            <p className="text-xs font-semibold">Cargando transcripción…</p>
          </div>
        )
      }
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-white p-8 text-center">
          <AlertTriangle className="h-8 w-8 text-amber-500" />
          <p className="text-sm font-bold text-slate-800">
            {loadState === 'not_found' ? 'No se encontró la transcripción.' : 'No se pudo cargar la transcripción.'}
          </p>
          {loadState === 'error' && loadError && <p className="text-xs text-slate-500 max-w-md">{loadError}</p>}
          <div className="flex gap-2">
            {loadState === 'error' && (
              <button
                type="button"
                onClick={reload}
                className="px-3 py-1.5 text-xs font-bold rounded-xl bg-[#002777] text-white hover:bg-[#001e5c] cursor-pointer"
              >
                Reintentar
              </button>
            )}
            <button
              type="button"
              onClick={onBackToDashboard}
              className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 cursor-pointer"
            >
              Volver al panel
            </button>
          </div>
        </div>
      )
    }

    return (
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 bg-slate-100 overflow-hidden divide-y lg:divide-y-0 lg:divide-x divide-slate-300">
        <TranscriptionViewer
          segments={segments}
          plainText={showLiveSegments ? undefined : record?.text}
          turnGapSec={record?.turn_gap_s}
          speakers={speakerEditing.speakers}
          diarization={record?.diarization}
          textMode={textMode}
          hasRawText={hasRawText}
          onTextModeChange={setTextMode}
          isLive={jobRunning}
          liveMessage={job && jobRunning ? getStageText(job) : undefined}
          canEdit={speakerEditing.canEdit}
          regenerateMode={regenerateMode}
          isBusy={isRegenerating || speakerEditing.isSaving}
          copied={exports.copiedTranscript}
          downloadMenuOpen={exports.transcriptMenuOpen}
          downloadMenuRef={exports.transcriptMenuRef}
          onToggleDownloadMenu={() => exports.setTranscriptMenuOpen((open) => !open)}
          onRegenerate={() => void handleRegenerate()}
          onOpenSpeakers={() => speakerEditing.setManagerOpen(true)}
          onCopy={() => void exports.copyTranscript()}
          onDownloadTxt={exports.downloadTranscriptTxt}
          onDownloadJson={exports.downloadTranscriptJson}
          onToggleMarked={(segment) => void speakerEditing.toggleMarked(segment)}
          onEditSegment={(segment) => setEditingSegmentId(segment.id || null)}
        />

        <SummaryPanel
          summaryText={summary.summaryText}
          summaryParagraphs={summary.summaryParagraphs}
          keyInsights={summary.keyInsights}
          summaryTemplates={summary.templates}
          selectedTemplate={summary.selectedTemplate}
          onSelectTemplate={summary.setSelectedTemplate}
          isSummaryReady={summary.isSummaryReady}
          isGeneratingSummary={summary.isGenerating}
          summaryStatus={summary.summaryStatus}
          isJobActive={jobRunning || !record}
          hasTranscriptContent={summary.hasTranscriptContent}
          hasCopiedSummary={exports.copiedSummary}
          showSummaryDownloadMenu={exports.summaryMenuOpen}
          summaryMenuRef={exports.summaryMenuRef}
          onToggleDownloadMenu={() => exports.setSummaryMenuOpen((open) => !open)}
          onGenerateSummary={() => void summary.generate()}
          onCopySummary={() => void exports.copySummary()}
          onDownloadMd={exports.downloadSummaryMd}
          onDownloadJson={exports.downloadSummaryJson}
        />
      </div>
    )
  }

  const cleanupNotes: string[] = []
  if (record?.silence_trimmed_s && record.silence_trimmed_s >= 5) {
    cleanupNotes.push(`${formatDuration(record.silence_trimmed_s)} de silencio omitidos`)
  }
  if (record?.cleanup?.fillers_removed) {
    cleanupNotes.push(`${record.cleanup.fillers_removed} muletillas eliminadas`)
  }

  const contentReady = Boolean(record) && !jobRunning && summary.hasTranscriptContent

  return (
    <div className="flex flex-col h-[calc(100vh-5.5rem)] max-w-[1700px] mx-auto bg-slate-100 font-sans rounded-2xl border border-slate-300/80 shadow-md overflow-hidden animate-fade-in">
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
              {renderStatusBadge()}
            </div>

            {record && (
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-slate-500 mt-0.5">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3 text-slate-400" />
                  <span>{formatDuration(record.duration_seconds)}</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3 text-slate-400" />
                  <span>
                    {speakersCount} {speakersCount === 1 ? 'interlocutor' : 'interlocutores'} · {record.segments?.length || 0}{' '}
                    fragmentos
                  </span>
                </span>
                <span>•</span>
                <span className="uppercase font-semibold text-slate-600">Idioma: {record.language || 'ES'}</span>
                {cleanupNotes.length > 0 && (
                  <>
                    <span>•</span>
                    <span>{cleanupNotes.join(' · ')}</span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {record && (
            <>
              <button
                type="button"
                onClick={() => void handleSaveToKB()}
                disabled={isSavingKB || record.saved_to_knowledge || !contentReady}
                className={`px-3 py-1.5 text-xs font-semibold rounded-xl border transition flex items-center gap-1.5 shadow-2xs ${
                  !contentReady
                    ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed opacity-60'
                    : record.saved_to_knowledge
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200 cursor-pointer'
                      : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 cursor-pointer'
                }`}
                title={
                  !contentReady
                    ? 'No hay transcripción disponible para guardar en la Base de Conocimiento'
                    : record.saved_to_knowledge
                      ? 'Ya está guardado en la Base de Conocimiento'
                      : 'Guardar en biblioteca de conocimiento para consultas del agente'
                }
              >
                <BookOpen className={`h-3.5 w-3.5 ${contentReady ? 'text-[#002777]' : 'text-slate-400'}`} />
                <span className="hidden md:inline">
                  {record.saved_to_knowledge ? 'En Base de Conocimiento' : 'Guardar en BC'}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setGenerateModalOpen(true)}
                disabled={!summary.isSummaryReady || !contentReady}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition shadow-2xs ${
                  contentReady && summary.isSummaryReady
                    ? 'bg-[#002777] hover:bg-[#001e5c] text-white cursor-pointer'
                    : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60'
                }`}
                title={
                  !contentReady
                    ? 'Se requiere una transcripción con diálogos para generar entregables'
                    : !summary.isSummaryReady
                      ? 'Genera el resumen para habilitar la creación de entregables'
                      : 'Generar Inventario (.xlsx) y Levantamiento (.docx)'
                }
              >
                <Sparkles
                  className={`h-3.5 w-3.5 ${contentReady && summary.isSummaryReady ? 'text-amber-300' : 'text-slate-400'}`}
                />
                <span>Generar</span>
              </button>
            </>
          )}
        </div>
      </header>


      {renderBody()}

      {speakerEditing.managerOpen && (
        <SpeakerManager
          speakers={speakerEditing.speakers}
          diarization={record?.diarization}
          isSaving={speakerEditing.isSaving}
          onSave={speakerEditing.saveSpeakers}
          onClose={() => speakerEditing.setManagerOpen(false)}
        />
      )}

      {editingSegment && editingSegment.id && (
        <SegmentEditModal
          key={editingSegment.id}
          segment={editingSegment}
          speakers={speakerEditing.speakers}
          isSaving={speakerEditing.isSaving}
          onClose={() => setEditingSegmentId(null)}
          onSaveText={(text) => speakerEditing.patchSegment(editingSegment.id as string, { text }, 'Texto actualizado.')}
          onAssignSpeaker={(speakerId) =>
            speakerEditing.patchSegment(editingSegment.id as string, { speaker_id: speakerId }, 'Interlocutor actualizado.')
          }
          onNewSpeaker={(name) =>
            speakerEditing.patchSegment(editingSegment.id as string, { new_speaker_name: name }, 'Interlocutor creado.')
          }
          onSplit={(at) => speakerEditing.splitSegment(editingSegment.id as string, at)}
        />
      )}

      <GenerateModal
        isOpen={generateModalOpen}
        transcriptionId={transcriptionId}
        meetingTitle={meetingTitle}
        onClose={() => setGenerateModalOpen(false)}
      />
    </div>
  )
}
