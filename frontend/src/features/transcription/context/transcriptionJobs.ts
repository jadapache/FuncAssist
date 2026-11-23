import type {
  TranscriptionProgress,
  TranscriptionSegment,
  TranscriptionStage,
} from '../api/transcriptionApi'
import { isTerminalStage, normalizeStage } from '../utils/transcriptionStages'

/** `server`: processed by the backend and followed over SSE. `browser`: Whisper in a Web Worker. */
export type JobKind = 'server' | 'browser'

export interface TranscriptionJob extends TranscriptionProgress {
  kind: JobKind
  title: string
  startedAt: number
  /** Segments already produced by an in-browser job, shown while it runs. */
  liveSegments: TranscriptionSegment[]
  /** Hidden from the floating widget (dismissed or auto-hidden after finishing). */
  toastHidden: boolean
}

export type JobsState = Record<string, TranscriptionJob>

export type NewJob = {
  id: string
  kind: JobKind
  title: string
  stage: TranscriptionStage
  progress?: number
  message?: string
  model_info?: string | null
  media_id?: string
}

export type JobsAction =
  /** Creates the job, replacing any previous state for the same id (new run or retry). */
  | { type: 'start'; job: NewJob; now?: number }
  /** Local update (upload progress, browser worker). Ignored for unknown jobs. */
  | { type: 'update'; id: string; patch: Partial<TranscriptionProgress> }
  /** Event from the progress stream or `/status`. `create` restores jobs not yet in the store. */
  | { type: 'server_progress'; progress: TranscriptionProgress; title?: string; create?: boolean; now?: number }
  | { type: 'append_segments'; id: string; segments: TranscriptionSegment[] }
  | { type: 'hide_toast'; id: string }
  | { type: 'remove'; id: string }
  /** Clears every job (logout). */
  | { type: 'reset' }

/**
 * Merges a progress update into a job. The overall percentage never goes back while the job
 * runs; a new non-terminal stage after a terminal one (retry) starts over.
 */
export function mergeProgress(prev: TranscriptionJob, patch: Partial<TranscriptionProgress>): TranscriptionJob {
  const prevStage = normalizeStage(prev.stage)
  const stage = normalizeStage(patch.stage ?? prev.stage)
  const terminal = isTerminalStage(stage)
  const restarted = isTerminalStage(prevStage) && !terminal
  const incoming = typeof patch.progress === 'number' && Number.isFinite(patch.progress) ? patch.progress : null

  let progress: number
  if (stage === 'complete') progress = 100
  else if (terminal) progress = prev.progress
  else if (restarted) progress = incoming ?? 0
  else progress = Math.max(prev.progress, incoming ?? prev.progress)

  const next: TranscriptionJob = {
    ...prev,
    ...patch,
    id: prev.id,
    kind: prev.kind,
    title: patch.title || prev.title,
    stage,
    status: stage,
    progress: Math.min(100, Math.max(0, Math.round(progress))),
    liveSegments: prev.liveSegments,
    toastHidden: restarted ? false : prev.toastHidden,
  }
  if (terminal) {
    next.eta = null
    next.eta_seconds = null
  }
  if (!terminal) {
    next.error = null
    next.error_code = null
  }
  if (restarted) next.liveSegments = []
  return next
}

function isDuplicate(prev: TranscriptionJob, progress: TranscriptionProgress): boolean {
  if (typeof progress.seq !== 'number' || typeof prev.seq !== 'number') return false
  if (progress.seq > prev.seq) return false
  const stage = normalizeStage(progress.stage)
  // A terminal state the job did not have yet is never a duplicate (e.g. interrupted after a restart).
  return !(isTerminalStage(stage) && stage !== normalizeStage(prev.stage))
}

export function createJob(job: NewJob, now: number): TranscriptionJob {
  const stage = normalizeStage(job.stage)
  return {
    id: job.id,
    kind: job.kind,
    title: job.title,
    media_id: job.media_id,
    stage,
    status: stage,
    progress: job.progress ?? 0,
    message: job.message,
    model_info: job.model_info ?? null,
    startedAt: now,
    liveSegments: [],
    toastHidden: false,
  }
}

export function jobsReducer(state: JobsState, action: JobsAction): JobsState {
  switch (action.type) {
    case 'start':
      return { ...state, [action.job.id]: createJob(action.job, action.now ?? Date.now()) }

    case 'update': {
      const prev = state[action.id]
      if (!prev) return state
      return { ...state, [action.id]: mergeProgress(prev, action.patch) }
    }

    case 'server_progress': {
      const { progress } = action
      const prev = state[progress.id]
      if (!prev) {
        if (!action.create) return state
        const created = createJob(
          {
            id: progress.id,
            kind: 'server',
            title: action.title || progress.title || 'Transcripción',
            stage: normalizeStage(progress.stage),
            media_id: progress.media_id,
          },
          action.now ?? Date.now(),
        )
        return { ...state, [progress.id]: mergeProgress(created, progress) }
      }
      if (isDuplicate(prev, progress)) return state
      return { ...state, [progress.id]: mergeProgress(prev, progress) }
    }

    case 'append_segments': {
      const prev = state[action.id]
      if (!prev || action.segments.length === 0) return state
      return { ...state, [action.id]: { ...prev, liveSegments: [...prev.liveSegments, ...action.segments] } }
    }

    case 'hide_toast': {
      const prev = state[action.id]
      if (!prev || prev.toastHidden) return state
      return { ...state, [action.id]: { ...prev, toastHidden: true } }
    }

    case 'remove': {
      if (!state[action.id]) return state
      const next = { ...state }
      delete next[action.id]
      return next
    }

    case 'reset':
      return Object.keys(state).length ? {} : state

    default:
      return state
  }
}
