import React from 'react'
import { Loader2, Star, VolumeX } from 'lucide-react'
import type { TranscriptionSegment } from '../api/transcriptionApi'
import { formatTimestamp, getSpeakerColor } from '../hooks/useTranscriptionActions'

interface SegmentListProps {
  segments: TranscriptionSegment[] | undefined
  plainText: string | undefined
  importantSegments: Set<number>
  activeProgressMessage?: string
  isJobActive?: boolean
  onToggleImportance: (index: number) => void
}

export const SegmentList: React.FC<SegmentListProps> = ({
  segments,
  plainText,
  importantSegments,
  activeProgressMessage,
  isJobActive,
  onToggleImportance,
}) => {
  // Empty state / Loading before any segments arrive
  if (!segments?.length && !plainText) {
    if (isJobActive) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
          <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
          <p className="text-xs font-bold text-slate-700">
            Decodificando audio...
          </p>
          <p className="text-[11px] text-slate-400 max-w-xs">
            Los segmentos y la identificación de interlocutores aparecerán aparecerán aquí a medida que se reconozcan.
          </p>
        </div>
      )
    }

    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
          <VolumeX className="h-6 w-6" />
        </div>
        <p className="text-xs font-bold text-slate-700">
          No se detectaron diálogos en la grabación.
        </p>
        <p className="text-[11px] text-slate-400 max-w-xs">
          El archivo procesado no contiene voz audible o segmentos de audio para transcribir.
        </p>
      </div>
    )
  }

  // Render segments (real-time stream or finished)
  if (segments && segments.length > 0) {
    return (
      <div className="space-y-3 max-w-3xl animate-fade-in">
        <p className="text-[11px] text-slate-400 italic mb-2">
          * Haz clic en cualquier segmento para marcarlo o desmarcarlo como <strong>importante</strong>.
        </p>

        {segments.map((seg, idx) => {
          const isImportant = importantSegments.has(idx)
          const speakerColorClass = getSpeakerColor(seg.speaker || 'Participante')
          const isLatestInLiveJob = isJobActive && idx === segments.length - 1

          return (
            <div
              key={idx}
              onClick={() => onToggleImportance(idx)}
              className={`group relative p-3.5 rounded-2xl border transition-all duration-150 cursor-pointer ${isImportant
                ? 'bg-amber-50/70 border-amber-300 ring-1 ring-amber-200/80 shadow-xs'
                : isLatestInLiveJob
                  ? 'bg-blue-50/40 border-blue-300/80 shadow-xs ring-1 ring-blue-200/50'
                  : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 shadow-2xs'
                }`}
            >
              {/* Segment Header */}
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-0.5 rounded-lg text-xs font-bold border shadow-2xs ${speakerColorClass}`}>
                    {seg.speaker || 'Participante'}
                  </span>
                  <span className="text-[11px] font-mono font-medium text-slate-400">
                    [{formatTimestamp(seg.start)}]
                  </span>
                  {isLatestInLiveJob && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-blue-100 text-blue-800">
                      <span className="h-1.5 w-1.5 rounded-full bg-blue-600 animate-ping" />
                      En vivo
                    </span>
                  )}
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
                      onToggleImportance(idx)
                    }}
                    className={`p-1 rounded-lg transition ${isImportant
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
                className={`text-sm leading-relaxed ${isImportant ? 'font-semibold text-slate-900' : 'text-slate-700'
                  }`}
              >
                {seg.text}
                {isLatestInLiveJob && (
                  <span className="inline-block w-1.5 h-4 ml-1 bg-[#002777] animate-pulse align-middle" />
                )}
              </p>
            </div>
          )
        })}

        {/* Live Streaming Indicator at the bottom of the list */}
        {isJobActive && (
          <div className="flex items-center gap-2.5 px-4 py-3 rounded-2xl bg-blue-50/80 border border-blue-200/80 text-xs text-[#002777] shadow-2xs animate-pulse">
            <Loader2 className="h-4 w-4 animate-spin text-[#002777]" />
            <span className="font-semibold">
              {activeProgressMessage || 'Transcribiendo siguientes turnos de voz en vivo...'}
            </span>
          </div>
        )}
      </div>
    )
  }

  // Render plain text fallback
  return (
    <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
      {plainText}
    </div>
  )
}
