/**
 * Overlapping windows for in-browser Whisper: 30 s windows advancing 25 s, so every boundary
 * falls inside the 5 s overlap of two windows. Each window "owns" the span between the middles
 * of its overlaps; a segment is kept only by the window that owns its midpoint, which removes
 * the duplicates and the words cut at window edges.
 */

export interface WindowPlan {
  index: number
  start: number
  end: number
  ownStart: number
  ownEnd: number
  isLast: boolean
}

export interface WhisperChunk {
  text?: string
  timestamp?: [number | null, number | null] | null
}

export interface TimedText {
  start: number
  end: number
  text: string
}

export function planWindows(totalSec: number, windowSec = 30, overlapSec = 5): WindowPlan[] {
  if (!(totalSec > 0)) return []
  const step = Math.max(1, windowSec - overlapSec)
  const half = overlapSec / 2
  const windows: WindowPlan[] = []
  let start = 0
  for (let index = 0; ; index++) {
    const end = Math.min(start + windowSec, totalSec)
    const isLast = end >= totalSec
    windows.push({
      index,
      start,
      end,
      ownStart: index === 0 ? 0 : start + half,
      ownEnd: isLast ? totalSec : start + step + half,
      isLast,
    })
    if (isLast) break
    start += step
  }
  return windows
}

const round2 = (value: number) => Math.round(value * 100) / 100

/**
 * Segments of one window in absolute time, keeping only those whose midpoint the window owns.
 * Without timestamped chunks the whole window text is used.
 */
export function segmentsFromWindow(window: WindowPlan, chunks: WhisperChunk[], fallbackText?: string): TimedText[] {
  const duration = window.end - window.start
  const result: TimedText[] = []

  const source: WhisperChunk[] =
    chunks.length > 0 ? chunks : fallbackText?.trim() ? [{ text: fallbackText, timestamp: [0, duration] }] : []

  let previousEnd = 0
  for (const chunk of source) {
    const text = (chunk.text || '').trim()
    if (!text) continue
    const relStart = chunk.timestamp?.[0] ?? previousEnd
    const relEndRaw = chunk.timestamp?.[1]
    const relEnd = relEndRaw === null || relEndRaw === undefined ? duration : relEndRaw
    const start = window.start + Math.min(Math.max(0, relStart), duration)
    const end = window.start + Math.min(Math.max(relStart, relEnd), duration)
    previousEnd = Math.max(previousEnd, relEnd)

    const mid = (start + end) / 2
    const owned = window.isLast ? mid >= window.ownStart && mid <= window.ownEnd : mid >= window.ownStart && mid < window.ownEnd
    if (owned) result.push({ start: round2(start), end: round2(end), text })
  }
  return result
}
