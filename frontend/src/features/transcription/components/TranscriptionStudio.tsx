import React from 'react'
import { ArrowLeft, Sparkles, Clock, Users, CheckCircle2, Loader2, BookOpen } from 'lucide-react'
import type { TranscriptionProgress } from '../api/transcriptionApi'
import { GenerateModal } from './GenerateModal'
import { TranscriptionViewer } from './TranscriptionViewer'
import { SummaryPanel } from './SummaryPanel'
import { SpeakerManager } from './SpeakerManager'
import {
  useTranscriptionActions,
  formatDuration,
} from '../hooks/useTranscriptionActions'

interface TranscriptionStudioProps {
  transcriptionId: string
  initialMeetingTitle?: string
  activeProgress?: TranscriptionProgress | null
  onBackToDashboard: () => void
  onRefreshData?: () => void
  onRetranscribe?: (transcriptionId: string, title?: string) => Promise<void>
}

export const TranscriptionStudio: React.FC<TranscriptionStudioProps> = ({
  transcriptionId,
  initialMeetingTitle,
  activeProgress,
  onBackToDashboard,
  onRefreshData,
  onRetranscribe,
}) => {
  const {
    transcriptionResult,
    importantSegments,
    isGeneratingSummary,
    isSavingKB,
    isRetranscribing,
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
    hasTranscriptContent,
    meetingTitle,
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
  } = useTranscriptionActions(
    transcriptionId,
    activeProgress,
    onRefreshData,
    initialMeetingTitle,
    onRetranscribe
  )

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
                disabled={isSavingKB || transcriptionResult.saved_to_knowledge || !hasTranscriptContent || isJobActive}
                className={`px-3 py-1.5 text-xs font-semibold rounded-xl border transition flex items-center gap-1.5 shadow-2xs ${
                  !hasTranscriptContent || isJobActive
                    ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed opacity-60'
                    : transcriptionResult.saved_to_knowledge
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200 cursor-pointer'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 cursor-pointer'
                }`}
                title={
                  !hasTranscriptContent
                    ? 'No hay transcripción disponible para guardar en la Base de Conocimiento'
                    : transcriptionResult.saved_to_knowledge
                    ? 'Ya está guardado en la Base de Conocimiento'
                    : 'Guardar en biblioteca de conocimiento para consultas del agente'
                }
              >
                <BookOpen className={`h-3.5 w-3.5 ${hasTranscriptContent && !isJobActive ? 'text-[#002777]' : 'text-slate-400'}`} />
                <span className="hidden md:inline">
                  {transcriptionResult.saved_to_knowledge ? 'En Base de Conocimiento' : 'Guardar en BC'}
                </span>
              </button>

              {/* Generar Documentos Button (Movido a la cabecera superior) */}
              <button
                type="button"
                onClick={() => setGenerateModalOpen(true)}
                disabled={!isSummaryReady || !hasTranscriptContent || isJobActive}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition shadow-2xs ${
                  hasTranscriptContent && isSummaryReady && !isJobActive
                    ? 'bg-[#002777] hover:bg-[#001e5c] text-white cursor-pointer'
                    : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60'
                }`}
                title={
                  !hasTranscriptContent
                    ? 'Se requiere una transcripción con diálogos para generar entregables'
                    : !isSummaryReady
                    ? 'Genera el resumen para habilitar la creación de entregables'
                    : 'Generar Inventario (.xlsx) y Levantamiento (.docx)'
                }
              >
                <Sparkles className={`h-3.5 w-3.5 ${hasTranscriptContent && isSummaryReady && !isJobActive ? 'text-amber-300' : 'text-slate-400'}`} />
                <span>Generar</span>
              </button>
            </>
          )}
        </div>
      </header>

      {/* Main Dual-Panel Workspace */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 bg-slate-100 overflow-hidden divide-y lg:divide-y-0 lg:divide-x divide-slate-300">
        {/* Left Panel: Transcripción */}
        <TranscriptionViewer
          transcriptionResult={transcriptionResult}
          importantSegments={importantSegments}
          activeProgressMessage={activeProgress?.message}
          isJobActive={isJobActive}
          isRetranscribing={isRetranscribing}
          hasCopiedTranscript={hasCopiedTranscript}
          showTranscriptDownloadMenu={showTranscriptDownloadMenu}
          transcriptMenuRef={transcriptMenuRef}
          onToggleDownloadMenu={() => setShowTranscriptDownloadMenu((prev) => !prev)}
          onRetranscribe={handleRetranscribe}
          onRenameClick={() => setShowRenameModal(true)}
          onCopyTranscript={handleCopyTranscript}
          onDownloadTranscriptTxt={handleDownloadTranscriptTxt}
          onDownloadTranscriptJson={handleDownloadTranscriptJson}
          onToggleSegmentImportance={toggleSegmentImportance}
        />

        {/* Right Panel: Resumen */}
        <SummaryPanel
          summaryParagraphs={summaryParagraphs}
          keyInsights={keyInsights}
          isSummaryReady={isSummaryReady}
          isGeneratingSummary={isGeneratingSummary}
          isJobActive={isJobActive}
          hasTranscriptContent={hasTranscriptContent}
          hasCopiedSummary={hasCopiedSummary}
          showSummaryDownloadMenu={showSummaryDownloadMenu}
          summaryMenuRef={summaryMenuRef}
          onToggleDownloadMenu={() => setShowSummaryDownloadMenu((prev) => !prev)}
          onGenerateSummary={handleGenerateSummary}
          onCopySummary={handleCopySummary}
          onDownloadTxt={handleDownloadSummaryTxt}
          onDownloadJson={handleDownloadSummaryJson}
        />
      </div>

      {/* Speaker Rename Modal */}
      <SpeakerManager
        isOpen={showRenameModal}
        speakerMap={speakerMap}
        onSpeakerChange={(speaker, newName) =>
          setSpeakerMap({
            ...speakerMap,
            [speaker]: newName,
          })
        }
        onSave={handleSaveSpeakerNames}
        onClose={() => setShowRenameModal(false)}
      />

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
