import React, { useMemo } from 'react'
import { Loader2, Pencil, Star, VolumeX } from 'lucide-react'
import type { TranscriptionSegment } from '../api/transcriptionApi'
import { formatTimestamp } from '../utils/time'
import { DEFAULT_TURN_GAP_S, groupTurns, type TextMode } from '../utils/turns'
import { speakerColorClass, type SpeakerEntry } from '../utils/speakers'

interface SegmentListProps {
  segments: TranscriptionSegment[]
  plainText?: string
  textMode: TextMode
  turnGapSec?: number
  speakers: SpeakerEntry[]
  /** A job is producing this transcription right now. */
  isLive: boolean
  liveMessage?: string
  canEdit: boolean
  onToggleMarked: (segment: TranscriptionSegment) => void
  onEditSegment: (segment: TranscriptionSegment) => void
}

export const SegmentList: React.FC<SegmentListProps> = ({
  segments,
  plainText,
  textMode,
  turnGapSec,
  speakers,
  isLive,
  liveMessage,
  canEdit,
  onToggleMarked,
  onEditSegment,
}) => {
  const turns = useMemo(
    () => groupTurns(segments, { gapSec: turnGapSec ?? DEFAULT_TURN_GAP_S, mode: textMode }),
    [segments, turnGapSec, textMode],
  )
  const lookup = useMemo(() => new Map(speakers.map((speaker) => [speaker.id, speaker])), [speakers])

  if (turns.length === 0 && !plainText?.trim()) {
    if (isLive) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
          <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
          <p className="text-xs font-bold text-slate-700">{liveMessage || 'Procesando…'}</p>
          <p className="text-[11px] text-slate-400 max-w-xs">
            El texto aparecerá aquí en cuanto esté disponible.
          </p>
        </div>
      )
    }
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
          <VolumeX className="h-6 w-6" />
        </div>
        <p className="text-xs font-bold text-slate-700">No se detectaron diálogos en la grabación.</p>
        <p className="text-[11px] text-slate-400 max-w-xs">
          El archivo procesado no contiene voz audible o segmentos de audio para transcribir.
        </p>
      </div>
    )
  }

  if (turns.length === 0) {
    return (
      <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
        {plainText}
      </div>
    )
  }

  const lastTurnIndex = turns.length - 1

  return (
    <div className="space-y-3 max-w-3xl animate-fade-in">
      {canEdit && (
        <p className="text-[11px] text-slate-400 italic mb-2">
          * Usa la estrella para marcar un fragmento como <strong>importante</strong> y el lápiz para corregir el
          texto, cambiar el interlocutor o dividirlo.
        </p>
      )}

      {turns.map((turn, turnIndex) => {
        const speaker = lookup.get(turn.speakerKey)
        const speakerName = speaker?.name || turn.speaker
        const colorClass = speakerColorClass(speaker?.colorIndex ?? 0)
        const isLatestLive = isLive && turnIndex === lastTurnIndex
        const hasMarked = turn.items.some((item) => item.segment.marked)

        return (
          <div
            key={turn.key}
            className={`group/turn relative p-3.5 rounded-2xl border transition-all duration-150 ${
              hasMarked
                ? 'bg-amber-50/50 border-amber-200'
                : isLatestLive
                  ? 'bg-blue-50/40 border-blue-300/80 ring-1 ring-blue-200/50'
                  : 'bg-white border-slate-200 shadow-2xs'
            }`}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`px-2.5 py-0.5 rounded-lg text-xs font-bold border shadow-2xs ${colorClass}`}>
                {speakerName}
              </span>
              <span className="text-[11px] font-mono font-medium text-slate-400">[{formatTimestamp(turn.start)}]</span>
              {isLatestLive && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-blue-100 text-blue-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-600 animate-ping" />
                  En vivo
                </span>
              )}
            </div>

            <div className="space-y-1">
              {turn.items.map(({ segment, index, text }) => (
                <div
                  key={segment.id || index}
                  className={`group/segment flex items-start gap-2 rounded-lg px-1.5 py-0.5 -mx-1.5 ${
                    segment.marked ? 'bg-amber-100/70' : canEdit ? 'hover:bg-slate-50' : ''
                  }`}
                >
                  <p
                    className={`flex-1 text-sm leading-relaxed ${
                      segment.marked ? 'font-semibold text-slate-900' : 'text-slate-700'
                    }`}
                  >
                    {text}
                    {segment.tags?.map((tag) => (
                      <span
                        key={tag}
                        className="ml-1.5 inline-block rounded-md bg-slate-100 px-1.5 py-px align-middle text-[10px] font-semibold text-slate-500"
                      >
                        {tag}
                      </span>
                    ))}
                  </p>
                  {canEdit && segment.id && (
                    <div
                      className={`flex items-center gap-0.5 shrink-0 transition ${
                        segment.marked ? 'opacity-100' : 'opacity-0 group-hover/segment:opacity-100 focus-within:opacity-100'
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => onToggleMarked(segment)}
                        className={`p-1 rounded-lg transition ${
                          segment.marked ? 'text-amber-500 hover:text-amber-600' : 'text-slate-400 hover:text-amber-500'
                        }`}
                        title={segment.marked ? 'Desmarcar de importante' : 'Marcar como importante'}
                      >
                        <Star className={`h-3.5 w-3.5 ${segment.marked ? 'fill-amber-400' : ''}`} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onEditSegment(segment)}
                        className="p-1 rounded-lg text-slate-400 hover:text-[#002777] transition"
                        title="Editar fragmento"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {isLive && (
        <div className="flex items-center gap-2.5 px-4 py-3 rounded-2xl bg-blue-50/80 border border-blue-200/80 text-xs text-[#002777] shadow-2xs animate-pulse">
          <Loader2 className="h-4 w-4 animate-spin text-[#002777]" />
          <span className="font-semibold">{liveMessage || 'Transcribiendo los siguientes fragmentos…'}</span>
        </div>
      )}
    </div>
  )
}
