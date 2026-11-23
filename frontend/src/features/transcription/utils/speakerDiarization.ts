/**
 * In-browser speaker diarization helpers (pure, no model code).
 *
 * Pipeline run by the worker:
 *  1. pyannote-segmentation-3.0 on 10 s windows of the speech-only audio → local speakers per window
 *     (powerset classes: 0 = no speech, 1-3 = one speaker, 4-6 = overlapping pairs).
 *  2. One WeSpeaker embedding per local speaker with enough speech in the window.
 *  3. Average-linkage agglomerative clustering on cosine distance → global speakers.
 *  4. Each Whisper segment takes the speaker that overlaps it most.
 */

export interface TimeSpan {
  start: number
  end: number
}

export interface PyannoteTurn extends TimeSpan {
  id: number
  confidence?: number
}

export interface LocalSpeaker {
  window: number
  localId: number
  /** Spans in the timeline of the audio passed to the worker (seconds). */
  spans: TimeSpan[]
  speechSec: number
}

export interface LabelledSpan extends TimeSpan {
  label: number
}

export const DIARIZATION_WINDOW_SEC = 10
export const MIN_EMBEDDING_SPEECH_SEC = 1
/** Cosine distance (1 − similarity) below which two speaker embeddings are the same person. */
export const DEFAULT_CLUSTER_THRESHOLD = 0.6
export const MAX_BROWSER_SPEAKERS = 8
const NEAREST_TURN_MAX_GAP_SEC = 2

export function planDiarizationWindows(totalSec: number, windowSec = DIARIZATION_WINDOW_SEC): TimeSpan[] {
  const windows: TimeSpan[] = []
  for (let start = 0; start < totalSec; start += windowSec) {
    windows.push({ start, end: Math.min(totalSec, start + windowSec) })
  }
  return windows
}

/** Single-speaker turns of one window, grouped by local speaker and shifted by the window offset. */
export function localSpeakers(turns: PyannoteTurn[], windowIndex: number, offsetSec: number): LocalSpeaker[] {
  const bySpeaker = new Map<number, LocalSpeaker>()
  for (const turn of turns) {
    if (turn.id < 1 || turn.id > 3 || turn.end <= turn.start) continue
    let speaker = bySpeaker.get(turn.id)
    if (!speaker) {
      speaker = { window: windowIndex, localId: turn.id, spans: [], speechSec: 0 }
      bySpeaker.set(turn.id, speaker)
    }
    speaker.spans.push({ start: offsetSec + turn.start, end: offsetSec + turn.end })
    speaker.speechSec += turn.end - turn.start
  }
  return [...bySpeaker.values()]
}

/** Concatenated samples of the given spans. */
export function gatherSamples(audio: Float32Array, sampleRate: number, spans: TimeSpan[]): Float32Array {
  const ranges = spans.map((span) => [
    Math.max(0, Math.floor(span.start * sampleRate)),
    Math.min(audio.length, Math.ceil(span.end * sampleRate)),
  ])
  const total = ranges.reduce((sum, [from, to]) => sum + Math.max(0, to - from), 0)
  const out = new Float32Array(total)
  let offset = 0
  for (const [from, to] of ranges) {
    if (to <= from) continue
    out.set(audio.subarray(from, to), offset)
    offset += to - from
  }
  return out
}

/** Embedding vector from a model output of shape [1, D] or [1, T, D] (mean over T). */
export function poolEmbedding(data: ArrayLike<number>, dims: readonly number[]): Float32Array {
  const dim = dims[dims.length - 1] ?? data.length
  const rows = Math.max(1, Math.floor(data.length / dim))
  const out = new Float32Array(dim)
  for (let r = 0; r < rows; r++) {
    for (let d = 0; d < dim; d++) out[d] += Number(data[r * dim + d]) / rows
  }
  return l2normalize(out)
}

export function l2normalize(vector: Float32Array): Float32Array {
  let norm = 0
  for (let i = 0; i < vector.length; i++) norm += vector[i] * vector[i]
  norm = Math.sqrt(norm)
  if (norm === 0) return vector
  const out = new Float32Array(vector.length)
  for (let i = 0; i < vector.length; i++) out[i] = vector[i] / norm
  return out
}

/** Cosine distance of two L2-normalised vectors. */
export function cosineDistance(a: Float32Array, b: Float32Array): number {
  let dot = 0
  for (let i = 0; i < a.length; i++) dot += a[i] * b[i]
  return 1 - dot
}

export interface ClusterOptions {
  threshold?: number
  /** Exact number of speakers when the user knows it. */
  numSpeakers?: number | null
  maxSpeakers?: number
}

interface Merge {
  a: number
  b: number
  distance: number
}

/**
 * Average-linkage agglomerative clustering (nearest-neighbour chain, O(n²)).
 * Returns one cluster label per embedding, numbered by first appearance.
 */
export function clusterEmbeddings(embeddings: Float32Array[], options: ClusterOptions = {}): number[] {
  const n = embeddings.length
  if (n === 0) return []
  if (n === 1) return [0]
  const threshold = options.threshold ?? DEFAULT_CLUSTER_THRESHOLD
  const maxSpeakers = Math.max(1, options.maxSpeakers ?? MAX_BROWSER_SPEAKERS)
  const target = options.numSpeakers && options.numSpeakers > 0 ? Math.min(options.numSpeakers, n) : null

  const dist = new Float64Array(n * n)
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const d = cosineDistance(embeddings[i], embeddings[j])
      dist[i * n + j] = d
      dist[j * n + i] = d
    }
  }
  const size = new Array<number>(n).fill(1)
  const active = new Array<boolean>(n).fill(true)
  let remaining = n
  const merges: Merge[] = []
  const chain: number[] = []

  while (remaining > 1) {
    if (chain.length === 0) chain.push(active.indexOf(true))
    const a = chain[chain.length - 1]
    const previous = chain.length > 1 ? chain[chain.length - 2] : -1
    let best = -1
    let bestDist = Infinity
    for (let k = 0; k < n; k++) {
      if (!active[k] || k === a) continue
      const d = dist[a * n + k]
      if (d < bestDist || (d === bestDist && k === previous)) {
        best = k
        bestDist = d
      }
    }
    if (best === previous) {
      chain.pop()
      chain.pop()
      merges.push({ a, b: best, distance: bestDist })
      // Lance-Williams update for average linkage; the merged cluster keeps index `a`.
      for (let k = 0; k < n; k++) {
        if (!active[k] || k === a || k === best) continue
        const d = (size[a] * dist[a * n + k] + size[best] * dist[best * n + k]) / (size[a] + size[best])
        dist[a * n + k] = d
        dist[k * n + a] = d
      }
      size[a] += size[best]
      active[best] = false
      remaining--
    } else {
      chain.push(best)
    }
  }

  merges.sort((x, y) => x.distance - y.distance)
  const parent = Array.from({ length: n }, (_, i) => i)
  const find = (x: number): number => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]]
      x = parent[x]
    }
    return x
  }
  let clusters = n
  for (const merge of merges) {
    const mustMerge = target !== null ? clusters > target : clusters > maxSpeakers
    if (!mustMerge && (target !== null || merge.distance > threshold)) break
    const ra = find(merge.a)
    const rb = find(merge.b)
    if (ra !== rb) {
      parent[rb] = ra
      clusters--
    }
  }

  const labels = new Map<number, number>()
  return embeddings.map((_, i) => {
    const root = find(i)
    if (!labels.has(root)) labels.set(root, labels.size)
    return labels.get(root) as number
  })
}

function overlap(a: TimeSpan, b: TimeSpan): number {
  return Math.max(0, Math.min(a.end, b.end) - Math.max(a.start, b.start))
}

/**
 * Speaker label of each segment: most overlapped speaker, else the nearest turn within 2 s,
 * else the previous segment's speaker (or the next one for leading segments).
 */
export function assignSpeakers(segments: TimeSpan[], turns: LabelledSpan[]): number[] {
  const sorted = [...turns].sort((x, y) => x.start - y.start)
  const raw: Array<number | null> = segments.map((segment) => {
    const totals = new Map<number, number>()
    for (const turn of sorted) {
      if (turn.start >= segment.end) break
      const o = overlap(segment, turn)
      if (o > 0) totals.set(turn.label, (totals.get(turn.label) ?? 0) + o)
    }
    if (totals.size > 0) {
      let bestLabel = -1
      let bestOverlap = -1
      for (const [label, total] of totals) {
        if (total > bestOverlap) {
          bestLabel = label
          bestOverlap = total
        }
      }
      return bestLabel
    }
    let nearest: number | null = null
    let nearestGap = NEAREST_TURN_MAX_GAP_SEC
    for (const turn of sorted) {
      const gap = turn.end < segment.start ? segment.start - turn.end : turn.start - segment.end
      if (gap >= 0 && gap <= nearestGap) {
        nearest = turn.label
        nearestGap = gap
      }
    }
    return nearest
  })

  const firstKnown = raw.find((label) => label !== null) ?? 0
  let last = firstKnown
  return raw.map((label) => {
    if (label === null) return last
    last = label
    return label
  })
}

/** Stable speaker ids (S1, S2…) in order of first appearance. */
export function speakerIdsByAppearance(labels: number[]): string[] {
  const ids = new Map<number, string>()
  return labels.map((label) => {
    if (!ids.has(label)) ids.set(label, `S${ids.size + 1}`)
    return ids.get(label) as string
  })
}
