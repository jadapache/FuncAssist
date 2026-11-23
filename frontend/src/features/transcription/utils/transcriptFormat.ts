import type { TranscriptionResult } from '../api/transcriptionApi'
import { formatTimestamp } from './time'
import { DEFAULT_TURN_GAP_S, groupTurns, type TextMode } from './turns'

type FormattableRecord = Pick<TranscriptionResult, 'segments' | 'text' | 'turn_gap_s'>

/** `[mm:ss] Speaker: text` per turn, the format the summary prompts expect. */
export function formatTranscriptForPrompt(record: FormattableRecord | null | undefined, mode: TextMode = 'clean'): string {
  if (!record) return ''
  const turns = groupTurns(record.segments, { gapSec: record.turn_gap_s ?? DEFAULT_TURN_GAP_S, mode })
  if (turns.length === 0) return (record.text || '').trim()
  return turns
    .map((turn) => `[${formatTimestamp(turn.start)}] ${turn.speaker}: ${turn.items.map((item) => item.text).join(' ')}`)
    .join('\n')
}

/**
 * Plain text export, one line per segment. Marked segments are wrapped in `**` and, with
 * `labelMarked`, prefixed with [IMPORTANTE].
 */
export function formatTranscriptForExport(
  record: FormattableRecord | null | undefined,
  mode: TextMode = 'clean',
  labelMarked = false,
): string {
  if (!record) return ''
  const turns = groupTurns(record.segments, { gapSec: 0, maxChars: Number.MAX_SAFE_INTEGER, mode })
  if (turns.length === 0) return (record.text || '').trim()
  const lines: string[] = []
  for (const turn of turns) {
    for (const item of turn.items) {
      const line = `[${formatTimestamp(item.segment.start)}] ${item.segment.speaker || turn.speaker}: ${item.text}`
      lines.push(item.segment.marked ? `**${labelMarked ? '[IMPORTANTE] ' : ''}${line}**` : line)
    }
  }
  return lines.join('\n\n')
}

/**
 * Keeps the beginning, the end and an even sample of the middle of a long transcript, for
 * browser models with a small context window.
 */
export function condenseTranscriptForBrowser(transcript: string, maxChars: number = 8000): string {
  if (!transcript || transcript.length <= maxChars) return transcript

  const lines = transcript.split('\n').filter((line) => line.trim().length > 0)
  if (lines.length <= 1) return transcript.slice(0, maxChars)

  const headBudget = Math.floor(maxChars * 0.3)
  const tailBudget = Math.floor(maxChars * 0.3)
  const midBudget = maxChars - headBudget - tailBudget

  const headLines: string[] = []
  let headChars = 0
  for (const line of lines) {
    if (headChars + line.length + 1 > headBudget) {
      if (headLines.length === 0) headLines.push(line.slice(0, headBudget))
      break
    }
    headLines.push(line)
    headChars += line.length + 1
  }

  const tailLines: string[] = []
  let tailChars = 0
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i]
    if (tailChars + line.length + 1 > tailBudget) {
      if (tailLines.length === 0) tailLines.unshift(line.slice(-tailBudget))
      break
    }
    tailLines.unshift(line)
    tailChars += line.length + 1
  }

  const midStart = headLines.length
  const midEnd = Math.max(midStart, lines.length - tailLines.length)
  const midPool = lines.slice(midStart, midEnd)
  const midLines: string[] = []
  if (midPool.length > 0) {
    const step = Math.max(1, Math.floor(midPool.length / 10))
    let midChars = 0
    for (let i = 0; i < midPool.length; i += step) {
      const line = midPool[i]
      if (midChars + line.length + 1 > midBudget) break
      midLines.push(line)
      midChars += line.length + 1
    }
  }

  const parts: string[] = []
  if (headLines.length > 0) parts.push(headLines.join('\n'))
  if (midLines.length > 0) parts.push('...\n' + midLines.join('\n'))
  if (tailLines.length > 0) parts.push('...\n' + tailLines.join('\n'))
  const result = parts.join('\n\n').trim()
  return result || transcript.slice(0, maxChars)
}

export function downloadTextFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export function safeFilename(title: string, fallback: string): string {
  return (title || fallback).replace(/[^a-zA-Z0-9_-]/g, '_')
}
