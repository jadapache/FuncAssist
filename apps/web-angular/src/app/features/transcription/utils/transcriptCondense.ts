/**
 * Pure helper moved verbatim from React `hooks/useTranscriptionActions.ts`.
 * Condenses long transcripts (head + sampled middle + tail) so they fit the
 * WebLLM browser context window.
 */
export function condenseTranscriptForBrowser(transcript: string, maxChars: number = 8000): string {
  if (!transcript || transcript.length <= maxChars) {
    return transcript
  }

  const lines = transcript.split('\n').filter((l) => l.trim().length > 0)
  if (lines.length <= 1) {
    return transcript.slice(0, maxChars)
  }

  const headBudget = Math.floor(maxChars * 0.30)
  const tailBudget = Math.floor(maxChars * 0.30)
  const midBudget = maxChars - headBudget - tailBudget

  const headLines: string[] = []
  let headChars = 0
  for (const line of lines) {
    if (headChars + line.length + 1 > headBudget) {
      if (headLines.length === 0) {
        headLines.push(line.slice(0, headBudget))
      }
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
      if (tailLines.length === 0) {
        tailLines.unshift(line.slice(-tailBudget))
      }
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
