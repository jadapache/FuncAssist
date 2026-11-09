import type { TranscriptionProgress } from '../api/transcriptionApi'

export const LOCAL_STORAGE_ACTIVE_JOBS = 'qa_active_transcription_jobs'

function isPersistableJob(
  id: string,
  job: TranscriptionProgress,
  clientJobIds?: Set<string>,
): boolean {
  if (id.startsWith('upload_')) return false
  if (clientJobIds?.has(id)) return false
  if (job.model_info === 'Whisper Web (Client)') return false
  const terminalStatuses = ['complete', 'failed', 'cancelled']
  return !terminalStatuses.includes(job.status)
}

export function loadStoredActiveJobs(): Record<string, TranscriptionProgress> {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_ACTIVE_JOBS)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, TranscriptionProgress>
    const valid: Record<string, TranscriptionProgress> = {}
    for (const [id, job] of Object.entries(parsed)) {
      if (isPersistableJob(id, job)) {
        valid[id] = job
      }
    }
    return valid
  } catch (err) {
    console.warn('Error reading active jobs from storage:', err)
    return {}
  }
}

export function saveActiveJobsToStorage(
  jobs: Record<string, TranscriptionProgress>,
  clientJobIds?: Set<string>,
): void {
  try {
    const activeOnly: Record<string, TranscriptionProgress> = {}
    for (const [id, job] of Object.entries(jobs)) {
      if (isPersistableJob(id, job, clientJobIds)) {
        activeOnly[id] = job
      }
    }
    localStorage.setItem(LOCAL_STORAGE_ACTIVE_JOBS, JSON.stringify(activeOnly))
  } catch (err) {
    console.warn('Could not persist active jobs to localStorage:', err)
  }
}

export function generateTranscriptionSlug(title: string, id: string): string {
  const cleaned = (title || 'transcripcion')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/[\s_-]+/g, '-')
    .slice(0, 50)
    .replace(/^-+|-+$/g, '')
  const shortId = id.slice(0, 8)
  return cleaned ? `${cleaned}-${shortId}` : id
}

