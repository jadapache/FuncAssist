import React from 'react'
import { Volume2, Users, Copy, Check, RotateCcw } from 'lucide-react'
import type { TranscriptionResult } from '../api/transcriptionApi'
import { SegmentList } from './SegmentList'
import { DownloadMenu } from './DownloadMenu'

interface TranscriptionViewerProps {
  transcriptionResult: TranscriptionResult | null
  importantSegments: Set<number>
  activeProgressMessage?: string
  isJobActive: boolean
  isRetranscribing?: boolean
  hasCopiedTranscript: boolean
  showTranscriptDownloadMenu: boolean
  transcriptMenuRef: React.RefObject<HTMLDivElement | null>
  onToggleDownloadMenu: () => void
  onRetranscribe?: () => void
  onRenameClick: () => void
  onCopyTranscript: () => void
  onDownloadTranscriptTxt: () => void
  onDownloadTranscriptJson: () => void
  onToggleSegmentImportance: (index: number) => void
}

export const TranscriptionViewer: React.FC<TranscriptionViewerProps> = ({
  transcriptionResult,
  importantSegments,
  activeProgressMessage,
  isJobActive,
  isRetranscribing = false,
  hasCopiedTranscript,
  showTranscriptDownloadMenu,
  transcriptMenuRef,
  onToggleDownloadMenu,
  onRetranscribe,
  onRenameClick,
  onCopyTranscript,
  onDownloadTranscriptTxt,
  onDownloadTranscriptJson,
  onToggleSegmentImportance,
}) => {
  const downloadItems = [
    {
      label: 'Texto (.txt)',
      description: 'Importantes en negrilla',
      icon: 'text' as const,
      color: 'blue' as const,
      onSelect: onDownloadTranscriptTxt,
    },
    {
      label: 'Estructurado (.json)',
      description: 'Con metadatos y marcas',
      icon: 'text' as const,
      color: 'amber' as const,
      onSelect: onDownloadTranscriptJson,
    },
  ]

  return (
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

        {/* Action Buttons: Regenerar transcripción, Renombrar interlocutores, Copiar, Descargar */}
        <div className="flex items-center gap-2">
          {/* Regenerar Transcripción */}
          <button
            type="button"
            onClick={onRetranscribe}
            disabled={isRetranscribing || isJobActive || (!transcriptionResult?.segments?.length && !transcriptionResult?.text)}
            className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
            title={
              isJobActive
                ? 'Procesamiento en curso...'
                : 'Regenerar transcripción'
            }
          >
            <RotateCcw className={`h-3.5 w-3.5 text-slate-600 ${isRetranscribing ? 'animate-spin text-[#002777]' : ''}`} />
          </button>

          {/* Renombrar interlocutores (Icono grupo de personas) */}
          <button
            type="button"
            onClick={onRenameClick}
            disabled={isJobActive || !transcriptionResult?.segments?.length}
            className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
            title={
              isJobActive
                ? 'Disponible al finalizar la transcripción'
                : 'Renombrar interlocutores'
            }
          >
            <Users className="h-3.5 w-3.5 text-[#002777]" />
          </button>

          <button
            type="button"
            onClick={onCopyTranscript}
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
          <DownloadMenu
            menuRef={transcriptMenuRef}
            isOpen={showTranscriptDownloadMenu}
            onToggle={onToggleDownloadMenu}
            items={downloadItems}
            disabled={!transcriptionResult?.segments?.length && !transcriptionResult?.text}
            title="Descargar transcripción"
          />
        </div>
      </div>

      {/* Transcript Content List */}
      <div className="relative flex-1 min-h-0 overflow-y-auto p-5 sm:p-6 bg-white space-y-3">
        {/* Live Progress Pill if currently transcribing */}
        {activeProgressMessage && isJobActive && (
          <div className="sticky top-0 z-20 mb-4 flex items-center gap-2 px-3.5 py-1.5 bg-slate-900/90 backdrop-blur-md text-white rounded-full shadow-lg border border-slate-700/60 text-xs animate-fade-in w-fit mx-auto">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            <span className="font-semibold text-slate-200">{activeProgressMessage}</span>
          </div>
        )}

        <SegmentList
          segments={transcriptionResult?.segments}
          plainText={transcriptionResult?.text}
          importantSegments={importantSegments}
          activeProgressMessage={activeProgressMessage}
          isJobActive={isJobActive}
          onToggleImportance={onToggleSegmentImportance}
        />
      </div>
    </section>
  )
}
