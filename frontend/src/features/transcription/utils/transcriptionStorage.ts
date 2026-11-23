import type { JobKind, TranscriptionJob } from '../context/transcriptionJobs'
import { isTerminalStage } from './transcriptionStages'

export const LOCAL_STORAGE_ACTIVE_JOBS = 'qa_active_transcription_jobs'

/**
 * Only a reference to each running job is kept locally; its real state comes from
 * `GET /transcription/jobs/active` after login.
 */
export interface StoredJobRef {
  id: string
  title: string
  kind: JobKind
  startedAt: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toRef(value: unknown, fallbackId?: string): StoredJobRef | null {
  if (!isRecord(value)) return null
  const id = typeof value.id === 'string' && value.id ? value.id : fallbackId
  if (!id) return null
  // Older versions stored the whole progress object: skip the ones already finished.
  const stage = typeof value.stage === 'string' ? value.stage : typeof value.status === 'string' ? value.status : ''
  if (stage && isTerminalStage(stage)) return null
  return {
    id,
    title: typeof value.title === 'string' && value.title ? value.title : 'Transcripción',
    kind: value.kind === 'browser' ? 'browser' : 'server',
    startedAt: typeof value.startedAt === 'number' ? value.startedAt : Date.now(),
  }
}

export function loadStoredJobRefs(): StoredJobRef[] {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_ACTIVE_JOBS)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    const entries: Array<[string | undefined, unknown]> = Array.isArray(parsed)
      ? parsed.map((item) => [undefined, item])
      : isRecord(parsed)
        ? Object.entries(parsed)
        : []
    const refs: StoredJobRef[] = []
    for (const [key, value] of entries) {
      const ref = toRef(value, key)
      if (ref) refs.push(ref)
    }
    return refs
  } catch (err) {
    console.warn('Error reading active jobs from storage:', err)
    return []
  }
}

export function saveJobRefs(jobs: TranscriptionJob[]): void {
  try {
    const refs: StoredJobRef[] = jobs
      .filter((job) => !isTerminalStage(job.stage))
      .map((job) => ({ id: job.id, title: job.title, kind: job.kind, startedAt: job.startedAt }))
    if (refs.length === 0) localStorage.removeItem(LOCAL_STORAGE_ACTIVE_JOBS)
    else localStorage.setItem(LOCAL_STORAGE_ACTIVE_JOBS, JSON.stringify(refs))
  } catch (err) {
    console.warn('Could not persist active jobs to localStorage:', err)
  }
}

export function generateTranscriptionSlug(title: string, id: string): string {
  const cleaned = (title || 'transcripcion')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/[\s_-]+/g, '-')
    .slice(0, 50)
    .replace(/^-+|-+$/g, '')
  const shortId = id.slice(0, 8)
  return cleaned ? `${cleaned}-${shortId}` : id
}
