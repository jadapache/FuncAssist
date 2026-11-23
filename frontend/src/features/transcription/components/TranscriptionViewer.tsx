import React from 'react'
import { Volume2, Users, Copy, Check, RotateCcw, Upload, UserX } from 'lucide-react'
import type { TranscriptionSegment } from '../api/transcriptionApi'
import type { TextMode } from '../utils/turns'
import type { SpeakerEntry } from '../utils/speakers'
import { SegmentList } from './SegmentList'
import { DownloadMenu } from './DownloadMenu'

interface TranscriptionViewerProps {
  segments: TranscriptionSegment[]
  plainText?: string
  turnGapSec?: number
  speakers: SpeakerEntry[]
  diarization?: string
  textMode: TextMode
  /** Show the Literal / Limpio switch (some segment differs from its verbatim text). */
  hasRawText: boolean
  onTextModeChange: (mode: TextMode) => void
  isLive: boolean
  liveMessage?: string
  canEdit: boolean
  /** null: regeneration not offered. */
  regenerateMode: 'server' | 'reupload' | null
  isBusy: boolean
  copied: boolean
  downloadMenuOpen: boolean
  downloadMenuRef: React.RefObject<HTMLDivElement | null>
  onToggleDownloadMenu: () => void
  onRegenerate: () => void
  onOpenSpeakers: () => void
  onCopy: () => void
  onDownloadTxt: () => void
  onDownloadJson: () => void
  onToggleMarked: (segment: TranscriptionSegment) => void
  onEditSegment: (segment: TranscriptionSegment) => void
}

const toolbarButton =
  'p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center'

export const TranscriptionViewer: React.FC<TranscriptionViewerProps> = ({
  segments,
  plainText,
  turnGapSec,
  speakers,
  diarization,
  textMode,
  hasRawText,
  onTextModeChange,
  isLive,
  liveMessage,
  canEdit,
  regenerateMode,
  isBusy,
  copied,
  downloadMenuOpen,
  downloadMenuRef,
  onToggleDownloadMenu,
  onRegenerate,
  onOpenSpeakers,
  onCopy,
  onDownloadTxt,
  onDownloadJson,
  onToggleMarked,
  onEditSegment,
}) => {
  const hasContent = segments.length > 0 || Boolean(plainText?.trim())
  const downloadItems = [
    {
      label: 'Texto (.txt)',
      description: 'Importantes en negrilla',
      icon: 'text' as const,
      color: 'blue' as const,
      onSelect: onDownloadTxt,
    },
    {
      label: 'Estructurado (.json)',
      description: 'Con metadatos y marcas',
      icon: 'text' as const,
      color: 'amber' as const,
      onSelect: onDownloadJson,
    },
  ]

  return (
    <section className="flex-1 flex flex-col min-h-0 bg-white overflow-hidden">
      <div className="min-h-11 px-4 py-1.5 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2 shrink-0 shadow-2xs">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-blue-100 text-[#002777]">
            <Volume2 className="h-3.5 w-3.5" />
          </div>
          <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide">Transcripción</h2>
          {diarization === 'none' && !isLive && hasContent && (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200"
              title="No se identificaron hablantes automáticamente. Puedes asignarlos con el lápiz de cada fragmento."
            >
              <UserX className="h-3 w-3" />
              Hablantes sin identificar
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {hasRawText && (
            <div className="flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200" role="group" aria-label="Versión del texto">
              {(['clean', 'raw'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => onTextModeChange(mode)}
                  aria-pressed={textMode === mode}
                  className={`px-2 py-0.5 rounded-md text-[11px] font-semibold transition cursor-pointer ${
                    textMode === mode ? 'bg-white text-[#002777] shadow-2xs' : 'text-slate-500 hover:text-slate-800'
                  }`}
                  title={mode === 'clean' ? 'Sin muletillas ni repeticiones' : 'Tal como se transcribió'}
                >
                  {mode === 'clean' ? 'Limpio' : 'Literal'}
                </button>
              ))}
            </div>
          )}

          {regenerateMode && (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={isBusy || isLive}
              className={toolbarButton}
              title={
                regenerateMode === 'server'
                  ? 'Regenerar transcripción con el motor configurado'
                  : 'Se transcribió en el navegador: vuelve a subir el archivo para transcribirlo de nuevo'
              }
            >
              {regenerateMode === 'server' ? (
                <RotateCcw className={`h-3.5 w-3.5 text-slate-600 ${isBusy ? 'animate-spin text-[#002777]' : ''}`} />
              ) : (
                <Upload className="h-3.5 w-3.5 text-slate-600" />
              )}
            </button>
          )}

          <button
            type="button"
            onClick={onOpenSpeakers}
            disabled={!canEdit}
            className={toolbarButton}
            title={canEdit ? 'Interlocutores' : 'Disponible al finalizar la transcripción'}
          >
            <Users className="h-3.5 w-3.5 text-[#002777]" />
          </button>

          <button
            type="button"
            onClick={onCopy}
            disabled={!hasContent}
            className={toolbarButton}
            title={copied ? 'Copiado al portapapeles' : 'Copiar texto de la transcripción'}
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5 text-slate-500" />}
          </button>

          <DownloadMenu
            menuRef={downloadMenuRef}
            isOpen={downloadMenuOpen}
            onToggle={onToggleDownloadMenu}
            items={downloadItems}
            disabled={!hasContent || isLive}
            title="Descargar transcripción"
          />
        </div>
      </div>

      <div className="relative flex-1 min-h-0 overflow-y-auto p-5 sm:p-6 bg-white space-y-3">
        {liveMessage && isLive && hasContent && (
          <div className="sticky top-0 z-20 mb-4 flex items-center gap-2 px-3.5 py-1.5 bg-slate-900/90 backdrop-blur-md text-white rounded-full shadow-lg border border-slate-700/60 text-xs animate-fade-in w-fit mx-auto">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            <span className="font-semibold text-slate-200">{liveMessage}</span>
          </div>
        )}

        <SegmentList
          segments={segments}
          plainText={plainText}
          textMode={textMode}
          turnGapSec={turnGapSec}
          speakers={speakers}
          isLive={isLive}
          liveMessage={liveMessage}
          canEdit={canEdit}
          onToggleMarked={onToggleMarked}
          onEditSegment={onEditSegment}
        />
      </div>
    </section>
  )
}
