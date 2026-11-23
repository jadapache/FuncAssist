import { getAuthHeaders } from '../../../core/api/config'
import { SseFrameParser, type SseFrame } from '../../chat/api/sseV2'
import { errorStatus, transcriptionApi, type TranscriptionProgress } from './transcriptionApi'
import { isStreamFinished, isTerminalStage, normalizeStage } from '../utils/transcriptionStages'

export interface ProgressStreamHandlers {
  onProgress: (progress: TranscriptionProgress) => void
  /** Terminal state reached (and, for `complete`, the summary finished). The stream is closed. */
  onFinished?: (last: TranscriptionProgress) => void
  /** The job does not exist (or belongs to another user). The stream is closed. */
  onNotFound?: () => void
  /** Authorization failure. The stream is closed. */
  onFatal?: (message: string) => void
}

export interface ProgressStreamOptions {
  url?: string
  fetchImpl?: typeof fetch
  headers?: () => Record<string, string>
  statusFetcher?: (id: string, signal: AbortSignal) => Promise<TranscriptionProgress>
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>
  /** Delay before each reconnection attempt; the last value repeats. */
  backoffMs?: readonly number[]
  /** Consecutive failed connections after which `/status` is polled between attempts. */
  pollAfterFailures?: number
  /** Reconnect when nothing (not even a heartbeat) arrives for this long. */
  idleTimeoutMs?: number
}

export interface ProgressStreamHandle {
  close: () => void
  isClosed: () => boolean
}

export const DEFAULT_BACKOFF_MS = [1000, 2000, 4000, 8000, 16000, 30000] as const

const defaultSleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const timer = setTimeout(resolve, ms)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        resolve()
      },
      { once: true },
    )
  })

type RawPayload = Partial<TranscriptionProgress> & { event?: string; status?: string }

/**
 * Follows a server job over SSE (`?protocol=v2`) with `fetch`, so the token travels in the
 * `Authorization` header. Reconnects with backoff, resumes with `Last-Event-ID`, drops
 * duplicates by `seq` and, after repeated connection failures, polls `/status` between attempts.
 */
export function openProgressStream(
  id: string,
  handlers: ProgressStreamHandlers,
  options: ProgressStreamOptions = {},
): ProgressStreamHandle {
  const url = options.url ?? transcriptionApi.getProgressStreamUrl(id)
  const fetchImpl = options.fetchImpl ?? ((input: RequestInfo | URL, init?: RequestInit) => fetch(input, init))
  const getHeaders = options.headers ?? getAuthHeaders
  const statusFetcher =
    options.statusFetcher ?? ((jobId: string, signal: AbortSignal) => transcriptionApi.getTranscriptionStatus(jobId, signal))
  const sleep = options.sleep ?? defaultSleep
  const backoff = options.backoffMs && options.backoffMs.length ? options.backoffMs : DEFAULT_BACKOFF_MS
  const pollAfterFailures = options.pollAfterFailures ?? 3
  const idleTimeoutMs = options.idleTimeoutMs ?? 45000

  const lifetime = new AbortController()
  let finished = false
  let lastSeq = -1
  let lastStage = ''

  const stop = () => {
    finished = true
    lifetime.abort()
  }

  /** Returns true once the job reached its final state. */
  const deliver = (raw: unknown): boolean => {
    if (!raw || typeof raw !== 'object') return false
    const data = raw as RawPayload
    if (data.event === 'heartbeat' || data.event === 'connected' || (data.stage as string) === 'heartbeat') return false
    if (data.event === 'error' && !data.id) {
      // Legacy "job not found" frame.
      handlers.onNotFound?.()
      stop()
      return true
    }

    const stage = normalizeStage(data.stage || data.status)
    if (typeof data.seq === 'number') {
      // A restarted backend may emit a terminal state (interrupted) without a higher seq.
      const isNewTerminal = isTerminalStage(stage) && stage !== lastStage
      if (data.seq <= lastSeq && !isNewTerminal) return false
      lastSeq = Math.max(lastSeq, data.seq)
    }
    lastStage = stage

    const progress: TranscriptionProgress = {
      ...data,
      id: data.id || id,
      stage,
      progress: typeof data.progress === 'number' ? data.progress : 0,
    }
    handlers.onProgress(progress)
    if (isStreamFinished(progress)) {
      handlers.onFinished?.(progress)
      stop()
      return true
    }
    return false
  }

  const handleFrame = (frame: SseFrame): boolean => {
    if (frame.event === 'heartbeat') return false
    if (frame.event && frame.event !== 'progress') return false
    try {
      return deliver(JSON.parse(frame.data))
    } catch {
      return false
    }
  }

  const connectOnce = async (): Promise<{ gotData: boolean }> => {
    const attempt = new AbortController()
    const abortAttempt = () => attempt.abort()
    lifetime.signal.addEventListener('abort', abortAttempt)
    let idleTimer: ReturnType<typeof setTimeout> | undefined
    const resetIdle = () => {
      if (idleTimer) clearTimeout(idleTimer)
      idleTimer = setTimeout(abortAttempt, idleTimeoutMs)
    }
    let gotData = false

    try {
      const headers: Record<string, string> = { Accept: 'text/event-stream', ...getHeaders() }
      if (lastSeq >= 0) headers['Last-Event-ID'] = String(lastSeq)
      resetIdle()
      const response = await fetchImpl(url, { headers, signal: attempt.signal, cache: 'no-store' })

      if (response.status === 404) {
        handlers.onNotFound?.()
        stop()
        return { gotData }
      }
      if (response.status === 401 || response.status === 403) {
        handlers.onFatal?.('No se pudo seguir el progreso: la sesión no está autorizada.')
        stop()
        return { gotData }
      }
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      const parser = new SseFrameParser()
      while (!finished) {
        const { done, value } = await reader.read()
        if (done) break
        resetIdle()
        for (const frame of parser.feed(decoder.decode(value, { stream: true }))) {
          gotData = true
          if (handleFrame(frame)) break
        }
      }
      if (!finished) {
        for (const frame of parser.flush()) {
          gotData = true
          if (handleFrame(frame)) break
        }
      }
      if (finished) await reader.cancel().catch(() => undefined)
    } catch {
      // Network error, idle timeout or abort: handled by the caller's retry loop.
    } finally {
      if (idleTimer) clearTimeout(idleTimer)
      lifetime.signal.removeEventListener('abort', abortAttempt)
    }
    return { gotData }
  }

  const pollOnce = async () => {
    try {
      deliver(await statusFetcher(id, lifetime.signal))
    } catch (err) {
      if (errorStatus(err) === 404) {
        handlers.onNotFound?.()
        stop()
      }
    }
  }

  const run = async () => {
    let failures = 0
    while (!finished && !lifetime.signal.aborted) {
      const { gotData } = await connectOnce()
      if (finished || lifetime.signal.aborted) break
      failures = gotData ? 1 : failures + 1
      if (failures >= pollAfterFailures) {
        await pollOnce()
        if (finished || lifetime.signal.aborted) break
      }
      await sleep(backoff[Math.min(failures - 1, backoff.length - 1)], lifetime.signal)
    }
  }

  void run()

  return {
    close: () => {
      if (!lifetime.signal.aborted) lifetime.abort()
      finished = true
    },
    isClosed: () => finished || lifetime.signal.aborted,
  }
}
