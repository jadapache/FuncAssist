/**
 * Format raw seconds into a human-readable ETA string.
 */
export function formatEtaSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return ''
  }
  if (seconds < 5) {
    return '< 5 s'
  }
  if (seconds < 60) {
    return `${Math.round(seconds)} s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  if (remainingSeconds === 0) {
    return `${minutes} min`
  }
  return `${minutes} min ${remainingSeconds} s`
}

/**
 * Format seconds into mm:ss timestamp format.
 */
export function formatAudioTime(seconds: number): string {
  const safeSec = Math.max(0, Math.floor(seconds))
  const mins = Math.floor(safeSec / 60)
  const secs = safeSec % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/**
 * Tracks wall-clock time against processed units to calculate smoothed ETA.
 */
export class EtaTracker {
  private startTime: number = 0
  private smoothedSpeed: number = 0

  start(): void {
    this.startTime = performance.now()
    this.smoothedSpeed = 0
  }

  update(currentUnits: number, totalUnits: number): string | null {
    if (totalUnits <= 0 || currentUnits <= 0 || currentUnits >= totalUnits) {
      return null
    }

    const elapsedSeconds = (performance.now() - this.startTime) / 1000
    if (elapsedSeconds < 0.8) {
      return null
    }

    const currentSpeed = currentUnits / elapsedSeconds
    this.smoothedSpeed = this.smoothedSpeed === 0
      ? currentSpeed
      : 0.7 * this.smoothedSpeed + 0.3 * currentSpeed

    if (this.smoothedSpeed <= 0) {
      return null
    }

    const remainingUnits = totalUnits - currentUnits
    const remainingSeconds = remainingUnits / this.smoothedSpeed
    return formatEtaSeconds(remainingSeconds)
  }
}
