import type { TranscriptionSegment } from '../api/transcriptionApi'

/** `clean`: text without fillers (default). `raw`: verbatim provider output. */
export type TextMode = 'clean' | 'raw'

export const DEFAULT_TURN_GAP_S = 8
export const MAX_TURN_CHARS = 600

export function segmentText(segment: TranscriptionSegment, mode: TextMode = 'clean'): string {
  const text = mode === 'raw' ? (segment.text_raw ?? segment.text) : segment.text
  return (text || '').trim()
}

/** Stable speaker key: `speaker_id`, or the display name for records without ids. */
export function speakerKey(segment: Pick<TranscriptionSegment, 'speaker_id' | 'speaker'>): string {
  return segment.speaker_id || segment.speaker || 'S1'
}

export interface TurnItem {
  segment: TranscriptionSegment
  /** Position in the original segment array. */
  index: number
  text: string
}

export interface TranscriptTurn {
  key: string
  speakerKey: string
  speaker: string
  start: number
  end: number
  items: TurnItem[]
}

export interface GroupTurnsOptions {
  gapSec?: number
  maxChars?: number
  mode?: TextMode
}

/**
 * Groups consecutive segments of the same speaker separated by less than `gapSec` into one
 * turn (at most ~`maxChars`). A pause never changes the speaker; it only starts a new turn.
 */
export function groupTurns(segments: TranscriptionSegment[] | undefined, options: GroupTurnsOptions = {}): TranscriptTurn[] {
  const gapSec = options.gapSec ?? DEFAULT_TURN_GAP_S
  const maxChars = options.maxChars ?? MAX_TURN_CHARS
  const mode = options.mode ?? 'clean'
  const turns: TranscriptTurn[] = []
  let current: TranscriptTurn | null = null
  let chars = 0

  ;(segments || []).forEach((segment, index) => {
    const text = segmentText(segment, mode)
    if (!text) return
    const key = speakerKey(segment)
    const start = Number(segment.start) || 0
    const end = Math.max(start, Number(segment.end) || start)
    const startsNewTurn =
      !current || current.speakerKey !== key || start - current.end >= gapSec || chars + text.length > maxChars

    if (startsNewTurn) {
      current = {
        key: `${segment.id || index}`,
        speakerKey: key,
        speaker: segment.speaker || 'Participante',
        start,
        end,
        items: [],
      }
      turns.push(current)
      chars = 0
    }
    const turn = current as TranscriptTurn
    turn.items.push({ segment, index, text })
    turn.end = Math.max(turn.end, end)
    chars += text.length + 1
  })

  return turns
}
