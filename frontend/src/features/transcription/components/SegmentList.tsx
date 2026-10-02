import React from 'react'
import { Loader2, Star } from 'lucide-react'
import type { TranscriptionSegment } from '../api/transcriptionApi'
import { formatTimestamp, getSpeakerColor } from '../hooks/useTranscriptionActions'

interface SegmentListProps {
  segments: TranscriptionSegment[] | undefined
  plainText: string | undefined
  importantSegments: Set<number>
  activeProgressMessage?: string
  onToggleImportance: (index: number) => void
}

export const SegmentList: React.FC<SegmentListProps> = ({
  segments,
  plainText,
  importantSegments,
  activeProgressMessage,
  onToggleImportance,
}) => {
  // Empty state / Loading
  if (!segments?.length && !plainText) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
        <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
        <p className="text-xs font-semibold text-slate-600">
          {activeProgressMessage || 'Procesando transcripción de audio...'}
        </p>
        <p className="text-[11px] text-slate-400 max-w-xs">
          Los segmentos y la identificación de interlocutores aparecerán aquí al completarse la transcripción y diarización.
        </p>
      </div>
    )
  }

  // Render segments if available
  if (segments && segments.length > 0) {
    return (
      <div className="space-y-3 max-w-3xl">
        <p className="text-[11px] text-slate-400 italic mb-2">
          * Haz clic en cualquier segmento para marcarlo o desmarcarlo como <strong>importante</strong>.
        </p>

        {segments.map((seg, idx) => {
          const isImportant = importantSegments.has(idx)
          const speakerColorClass = getSpeakerColor(seg.speaker || 'Participante')

          return (
            <div
              key={idx}
              onClick={() => onToggleImportance(idx)}
              className={`group relative p-3.5 rounded-2xl border transition-all duration-150 cursor-pointer ${
                isImportant
                  ? 'bg-amber-50/70 border-amber-300 ring-1 ring-amber-200/80 shadow-xs'
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
    )
  }

  // Render plain text fallback
  return (
    <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
      {plainText}
    </div>
  )
}
