/**
 * Remaining seconds from measured throughput: units processed so far over the elapsed wall time.
 * Returns null until there is enough signal (some progress and at least `minElapsedSec`).
 *
 * A cumulative average is already stable for Whisper windows of similar cost, so no extra
 * smoothing is applied.
 */
export function estimateRemainingSeconds(
  processedUnits: number,
  totalUnits: number,
  elapsedSec: number,
  minElapsedSec = 1,
): number | null {
  if (!(totalUnits > 0) || !(processedUnits > 0) || !(elapsedSec >= minElapsedSec)) return null
  if (processedUnits >= totalUnits) return 0
  const unitsPerSecond = processedUnits / elapsedSec
  if (!(unitsPerSecond > 0)) return null
  return (totalUnits - processedUnits) / unitsPerSecond
}
