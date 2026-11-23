/**
 * Energy-based voice activity detection for the in-browser path.
 *
 * Silences longer than `minSilenceSec` are cut (keeping `marginSec` of audio next to the speech),
 * the remaining speech is concatenated and a time map converts the timestamps Whisper returns
 * back to the original timeline. Short pauses are part of speech and are never cut.
 */

export interface SpeechRegion {
  start: number
  end: number
}

export interface TimeMapEntry {
  /** Start of the region in the concatenated (speech only) audio, in seconds. */
  compactStart: number
  /** Start of the region in the original audio, in seconds. */
  originalStart: number
  duration: number
}

export interface VadOptions {
  frameMs?: number
  minSilenceSec?: number
  marginSec?: number
  /** dB above the noise floor (10th percentile of frame energy) that counts as speech. */
  thresholdOffsetDb?: number
  minThresholdDb?: number
  maxThresholdDb?: number
}

const SILENT_DB = -100

export function frameEnergiesDb(samples: Float32Array, frameSize: number): Float32Array {
  const frames = Math.ceil(samples.length / frameSize)
  const energies = new Float32Array(frames)
  for (let f = 0; f < frames; f++) {
    const start = f * frameSize
    const end = Math.min(start + frameSize, samples.length)
    let sum = 0
    for (let i = start; i < end; i++) sum += samples[i] * samples[i]
    const rms = Math.sqrt(sum / Math.max(1, end - start))
    energies[f] = rms > 0 ? Math.max(SILENT_DB, 20 * Math.log10(rms)) : SILENT_DB
  }
  return energies
}

export function speechThresholdDb(energies: Float32Array, options: VadOptions = {}): number {
  const offset = options.thresholdOffsetDb ?? 6
  const min = options.minThresholdDb ?? -50
  const max = options.maxThresholdDb ?? -25
  if (energies.length === 0) return min
  const sorted = Array.from(energies).sort((a, b) => a - b)
  const noiseFloor = sorted[Math.floor(sorted.length * 0.1)]
  return Math.min(max, Math.max(min, noiseFloor + offset))
}

/** Regions (seconds) that contain speech. Empty when the audio has no speech at all. */
export function detectSpeechRegions(samples: Float32Array, sampleRate: number, options: VadOptions = {}): SpeechRegion[] {
  const frameMs = options.frameMs ?? 30
  const minSilenceSec = options.minSilenceSec ?? 2
  const marginSec = options.marginSec ?? 0.3
  const total = samples.length / sampleRate
  if (samples.length === 0) return []

  const frameSize = Math.max(1, Math.round((sampleRate * frameMs) / 1000))
  const frameSec = frameSize / sampleRate
  const energies = frameEnergiesDb(samples, frameSize)
  const threshold = speechThresholdDb(energies, options)

  const isSpeech = (f: number) => energies[f] >= threshold
  let anySpeech = false
  for (let f = 0; f < energies.length; f++) {
    if (isSpeech(f)) {
      anySpeech = true
      break
    }
  }
  if (!anySpeech) return []

  // Silent runs long enough to cut, as [start, end) in seconds.
  const cuts: SpeechRegion[] = []
  let runStart = -1
  for (let f = 0; f <= energies.length; f++) {
    const silent = f < energies.length && !isSpeech(f)
    if (silent && runStart < 0) runStart = f
    if (!silent && runStart >= 0) {
      const startSec = runStart * frameSec
      const endSec = Math.min(total, f * frameSec)
      if (endSec - startSec >= minSilenceSec) {
        const cutStart = runStart === 0 ? 0 : startSec + marginSec
        const cutEnd = f >= energies.length ? total : endSec - marginSec
        if (cutEnd > cutStart) cuts.push({ start: cutStart, end: cutEnd })
      }
      runStart = -1
    }
  }

  const regions: SpeechRegion[] = []
  let cursor = 0
  for (const cut of cuts) {
    if (cut.start > cursor) regions.push({ start: cursor, end: cut.start })
    cursor = Math.max(cursor, cut.end)
  }
  if (cursor < total) regions.push({ start: cursor, end: total })
  return regions.filter((region) => region.end - region.start > 1e-6)
}

/** Concatenates the speech regions. Without cuts the original array is returned as is. */
export function buildCompactAudio(
  samples: Float32Array,
  sampleRate: number,
  regions: SpeechRegion[],
): { audio: Float32Array; timeMap: TimeMapEntry[] } {
  const total = samples.length / sampleRate
  if (regions.length === 1 && regions[0].start <= 0 && regions[0].end >= total) {
    return { audio: samples, timeMap: [{ compactStart: 0, originalStart: 0, duration: total }] }
  }

  const bounds = regions.map((region) => ({
    from: Math.max(0, Math.round(region.start * sampleRate)),
    to: Math.min(samples.length, Math.round(region.end * sampleRate)),
  }))
  const length = bounds.reduce((sum, b) => sum + Math.max(0, b.to - b.from), 0)
  const audio = new Float32Array(length)
  const timeMap: TimeMapEntry[] = []
  let write = 0
  for (const b of bounds) {
    const count = Math.max(0, b.to - b.from)
    if (count === 0) continue
    audio.set(samples.subarray(b.from, b.to), write)
    timeMap.push({ compactStart: write / sampleRate, originalStart: b.from / sampleRate, duration: count / sampleRate })
    write += count
  }
  return { audio, timeMap }
}

/**
 * Converts a time in the concatenated audio back to the original timeline. With `isEnd`, a time
 * exactly on the joint between two regions maps to the end of the earlier one (segment ends).
 */
export function remapTime(compactTime: number, timeMap: TimeMapEntry[], isEnd = false): number {
  if (timeMap.length === 0) return compactTime
  let lo = 0
  let hi = timeMap.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (timeMap[mid].compactStart <= compactTime) lo = mid
    else hi = mid - 1
  }
  if (isEnd && lo > 0 && Math.abs(compactTime - timeMap[lo].compactStart) < 1e-6) {
    const previous = timeMap[lo - 1]
    return previous.originalStart + previous.duration
  }
  const entry = timeMap[lo]
  const offset = Math.min(Math.max(0, compactTime - entry.compactStart), entry.duration)
  return entry.originalStart + offset
}
