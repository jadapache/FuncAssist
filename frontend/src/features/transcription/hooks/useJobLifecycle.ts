import { useEffect, useMemo, useRef, type Dispatch } from 'react'
import { transcriptionApi } from '../api/transcriptionApi'
import type { JobsAction, JobsState, TranscriptionJob } from '../context/transcriptionJobs'
import { loadStoredJobRefs, saveJobRefs } from '../utils/transcriptionStorage'
import { isStreamFinished, isTerminalStage } from '../utils/transcriptionStages'
import type { ToastApi } from './useTranscriptionJobRunners'
import { useLatest } from './useLatest'

/** Finished jobs (complete or cancelled) leave the store, and the floating widget, after this delay. */
export const FINISHED_JOB_TTL_MS = 4000

/**
 * Restores the user's running jobs after login from `GET /jobs/active` and keeps a small
 * reference list in localStorage. Browser jobs cannot survive a reload: the user is told.
 */
export function useJobPersistence(options: {
  jobs: TranscriptionJob[]
  dispatch: Dispatch<JobsAction>
  enabled: boolean
  toast: ToastApi
}) {
  const { jobs, dispatch, enabled } = options
  const toastRef = useLatest(options.toast)
  const restoredRef = useRef(false)

  useEffect(() => {
    if (!enabled) {
      restoredRef.current = false
      dispatch({ type: 'reset' })
      return
    }
    let cancelled = false
    const refs = loadStoredJobRefs()
    restoredRef.current = true

    const lostBrowserJobs = refs.filter((ref) => ref.kind === 'browser')
    if (lostBrowserJobs.length > 0) {
      toastRef.current.warning(
        lostBrowserJobs.map((ref) => `«${ref.title}»`).join(', '),
        'Se interrumpió la transcripción en el navegador al recargar la página',
      )
    }

    const titles = new Map(refs.map((ref) => [ref.id, ref.title]))
    const serverRefs = refs.filter((ref) => ref.kind === 'server')
    const restore = async () => {
      try {
        const active = await transcriptionApi.getActiveTranscriptionJobs()
        if (cancelled) return
        for (const progress of active) {
          dispatch({ type: 'server_progress', progress, title: progress.title || titles.get(progress.id), create: true })
        }
      } catch {
        // Older backend without /jobs/active: ask for the jobs this browser knew about.
        for (const ref of serverRefs) {
          try {
            const progress = await transcriptionApi.getTranscriptionStatus(ref.id)
            if (cancelled) return
            if (!isTerminalStage(progress.stage)) {
              dispatch({ type: 'server_progress', progress, title: ref.title, create: true })
            }
          } catch {
            // Unknown job: nothing to restore.
          }
        }
      }
    }
    void restore()
    return () => {
      cancelled = true
    }
  }, [enabled, dispatch, toastRef])

  const refsKey = useMemo(
    () =>
      jobs
        .filter((job) => !isTerminalStage(job.stage))
        .map((job) => `${job.id}:${job.kind}`)
        .sort()
        .join(','),
    [jobs],
  )
  const jobsRef = useLatest(jobs)

  useEffect(() => {
    // Never overwrite the stored list before it has been read.
    if (!enabled || !restoredRef.current) return
    saveJobRefs(jobsRef.current)
  }, [refsKey, enabled, jobsRef])
}

/**
 * Side effects of stage changes: refresh the list and notify on completion or failure, and
 * remove finished jobs after FINISHED_JOB_TTL_MS. Failed and interrupted jobs stay until the
 * user dismisses or retries them.
 */
export function useJobNotifications(options: {
  jobs: TranscriptionJob[]
  jobsRef: { readonly current: JobsState }
  dispatch: Dispatch<JobsAction>
  toast: ToastApi
  onCompleted: (job: TranscriptionJob) => void
}) {
  const { jobs, jobsRef, dispatch } = options
  const callbacksRef = useLatest({ toast: options.toast, onCompleted: options.onCompleted })
  const stagesRef = useRef(new Map<string, string>())
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  useEffect(() => {
    const previous = stagesRef.current
    const next = new Map<string, string>()
    const { toast, onCompleted } = callbacksRef.current

    for (const job of jobs) {
      next.set(job.id, job.stage)
      const before = previous.get(job.id)
      if (before !== undefined && before !== job.stage) {
        if (job.stage === 'complete') {
          onCompleted(job)
          toast.success(`«${job.title}» se transcribió correctamente.`)
        } else if (job.stage === 'failed') {
          toast.error(job.error || 'Error durante la transcripción.', `No se pudo transcribir «${job.title}»`)
        } else if (job.stage === 'interrupted') {
          toast.warning('Puedes reintentarla desde la transcripción.', `Se interrumpió «${job.title}»`)
        }
      }

      const timers = timersRef.current
      const removable = isStreamFinished(job) && (job.stage === 'complete' || job.stage === 'cancelled')
      if (removable && !timers.has(job.id)) {
        timers.set(
          job.id,
          setTimeout(() => {
            timers.delete(job.id)
            const current = jobsRef.current[job.id]
            if (current && isStreamFinished(current) && (current.stage === 'complete' || current.stage === 'cancelled')) {
              dispatch({ type: 'remove', id: job.id })
            }
          }, FINISHED_JOB_TTL_MS),
        )
      } else if (!removable && timers.has(job.id)) {
        clearTimeout(timers.get(job.id))
        timers.delete(job.id)
      }
    }
    stagesRef.current = next
  }, [jobs, jobsRef, dispatch, callbacksRef])

  useEffect(() => {
    const timers = timersRef.current
    return () => {
      for (const timer of timers.values()) clearTimeout(timer)
      timers.clear()
    }
  }, [])
}

/** Warns before leaving the page while a browser job runs (it would be lost). */
export function useBeforeUnloadGuard(jobs: TranscriptionJob[]) {
  const hasBrowserJob = jobs.some((job) => job.kind === 'browser' && !isTerminalStage(job.stage))
  useEffect(() => {
    if (!hasBrowserJob) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasBrowserJob])
}
