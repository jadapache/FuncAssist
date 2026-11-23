/**
 * Pure helpers moved verbatim from React `hooks/useTranscriptionActions.ts`
 * (same export names; `condenseTranscriptForBrowser` lives in `./transcriptCondense`).
 */

export function formatDuration(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs < 10 ? '0' : ''}${secs}`
}

export function formatTimestamp(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`
}

/** Groups consecutive segments into speaker turns for the summary prompt (private helper in React). */
export function formatSegmentsForPrompt(
  segments?: Array<{ start?: number; end?: number; speaker?: string; text?: string }>,
  rawText?: string,
): string {
  if (segments && segments.length > 0) {
    const lines: string[] = []
    let currentSpeaker: string | null = null
    let currentStart = 0
    let currentLastEnd = 0
    let currentTexts: string[] = []
    let currentChars = 0

    const flush = () => {
      if (currentTexts.length > 0 && currentSpeaker !== null) {
        const m = Math.floor(currentStart / 60)
        const s = Math.floor(currentStart % 60)
        const ts = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
        const merged = currentTexts.join(' ').trim()
        if (merged) {
          lines.push(`[${ts}] ${currentSpeaker}: ${merged}`)
        }
      }
      currentTexts = []
      currentChars = 0
    }

    for (const seg of segments) {
      const spk = seg.speaker || 'Participante'
      const txt = (seg.text || '').trim()
      if (!txt) continue
      const start = seg.start || 0
      const end = seg.end || start + 2.0

      const silenceGap = currentTexts.length > 0 ? start - currentLastEnd : 0
      const isSpeakerChange = spk !== currentSpeaker
      const isTurnTooLong = currentChars + txt.length > 600
      const isGap = silenceGap > 5.0

      if (isSpeakerChange || isTurnTooLong || isGap) {
        flush()
        currentSpeaker = spk
        currentStart = start
      }

      currentTexts.push(txt)
      currentChars += txt.length + 1
      currentLastEnd = end
    }
    flush()

    if (lines.length > 0) {
      return lines.join('\n')
    }
  }
  return rawText || ''
}

export const SPEAKER_COLORS = [
  'bg-blue-50 text-blue-700 border-blue-200',
  'bg-emerald-50 text-emerald-700 border-emerald-200',
  'bg-purple-50 text-purple-700 border-purple-200',
  'bg-amber-50 text-amber-800 border-amber-200',
  'bg-rose-50 text-rose-700 border-rose-200',
  'bg-cyan-50 text-cyan-700 border-cyan-200',
]

export function getSpeakerColor(speakerName: string): string {
  let hash = 0
  for (let i = 0; i < speakerName.length; i++) {
    hash = speakerName.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % SPEAKER_COLORS.length
  return SPEAKER_COLORS[index]
}

export function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
