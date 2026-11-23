import type { TranscriptionResult } from '../api/transcriptionApi'
import { speakerKey } from './turns'

export const SPEAKER_COLORS = [
  'bg-blue-50 text-blue-700 border-blue-200',
  'bg-emerald-50 text-emerald-700 border-emerald-200',
  'bg-purple-50 text-purple-700 border-purple-200',
  'bg-amber-50 text-amber-800 border-amber-200',
  'bg-rose-50 text-rose-700 border-rose-200',
  'bg-cyan-50 text-cyan-700 border-cyan-200',
  'bg-lime-50 text-lime-800 border-lime-200',
  'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200',
]

export const SPEAKER_DOT_COLORS = [
  'bg-blue-500',
  'bg-emerald-500',
  'bg-purple-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-cyan-500',
  'bg-lime-500',
  'bg-fuchsia-500',
]

export function speakerColorClass(colorIndex: number): string {
  const index = Number.isFinite(colorIndex) && colorIndex >= 0 ? colorIndex : 0
  return SPEAKER_COLORS[index % SPEAKER_COLORS.length]
}

export function speakerDotClass(colorIndex: number): string {
  const index = Number.isFinite(colorIndex) && colorIndex >= 0 ? colorIndex : 0
  return SPEAKER_DOT_COLORS[index % SPEAKER_DOT_COLORS.length]
}

export interface SpeakerEntry {
  id: string
  name: string
  colorIndex: number
  segmentCount: number
}

/**
 * Speakers of a transcription in order of appearance. Uses the `speakers` map when present;
 * older records without it get one entry per distinct name. Colors come from `color_index`, so
 * they do not change when a speaker is renamed.
 */
export function listSpeakers(
  record: Pick<TranscriptionResult, 'speakers' | 'segments'> | null | undefined,
): SpeakerEntry[] {
  if (!record) return []
  const map = record.speakers || {}
  const entries = new Map<string, SpeakerEntry>()
  let nextColor = 0

  for (const segment of record.segments || []) {
    const id = speakerKey(segment)
    const existing = entries.get(id)
    if (existing) {
      existing.segmentCount += 1
      continue
    }
    const info = map[id]
    entries.set(id, {
      id,
      name: info?.name || segment.speaker || id,
      colorIndex: typeof info?.color_index === 'number' ? info.color_index : nextColor,
      segmentCount: 1,
    })
    nextColor += 1
  }

  // Speakers in the map without segments (e.g. just created) are still listed.
  for (const [id, info] of Object.entries(map)) {
    if (entries.has(id)) continue
    entries.set(id, {
      id,
      name: info.name || id,
      colorIndex: typeof info.color_index === 'number' ? info.color_index : nextColor++,
      segmentCount: 0,
    })
  }
  return Array.from(entries.values())
}

export function speakerLookup(speakers: SpeakerEntry[]): Map<string, SpeakerEntry> {
  return new Map(speakers.map((speaker) => [speaker.id, speaker]))
}
