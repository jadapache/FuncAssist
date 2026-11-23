const pad = (value: number) => value.toString().padStart(2, '0')

/** `mm:ss`, or `h:mm:ss` from one hour on. */
export function formatTimestamp(seconds: number): string {
  const safe = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0
  const hours = Math.floor(safe / 3600)
  const mins = Math.floor((safe % 3600) / 60)
  const secs = safe % 60
  return hours > 0 ? `${hours}:${pad(mins)}:${pad(secs)}` : `${pad(mins)}:${pad(secs)}`
}

/** Human duration: `1 h 05 min`, `12 min 30 s`, `45 s`. */
export function formatDuration(seconds: number): string {
  const safe = Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds) : 0
  const hours = Math.floor(safe / 3600)
  const mins = Math.floor((safe % 3600) / 60)
  const secs = safe % 60
  if (hours > 0) return `${hours} h ${pad(mins)} min`
  if (mins > 0) return secs > 0 ? `${mins} min ${secs} s` : `${mins} min`
  return `${secs} s`
}

/** Remaining time text; empty when unknown. */
export function formatEtaSeconds(seconds: number | null | undefined): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return ''
  if (seconds < 5) return '< 5 s'
  if (seconds < 60) return `~${Math.round(seconds)} s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    return `~${hours} h ${pad(minutes % 60)} min`
  }
  return rest === 0 ? `~${minutes} min` : `~${minutes} min ${rest} s`
}

/** ETA of a progress payload: numeric `eta_seconds` first, then the legacy text. */
export function formatProgressEta(progress: { eta_seconds?: number | null; eta?: string | null }): string | null {
  const fromSeconds = formatEtaSeconds(progress.eta_seconds)
  if (fromSeconds) return fromSeconds
  return progress.eta || null
}
