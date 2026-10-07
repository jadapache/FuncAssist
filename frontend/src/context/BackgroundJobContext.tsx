import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { api } from '../api/client'
import { transcriptionApi } from '../features/transcription/api/transcriptionApi'
import { useToast } from './ToastContext'

export interface BackgroundJobItem {
  id: string
  type: 'transcription' | 'download' | 'processing'
  title: string
  progress: number
  status:
    | 'pending'
    | 'uploading'
    | 'preprocessing'
    | 'transcribing'
    | 'diarizing'
    | 'summarizing'
    | 'complete'
    | 'failed'
    | 'cancelled'
  stageText?: string
  eta?: string | null
  speedOrSize?: string | null
  onCancel?: () => void
  onClick?: () => void
  onDismiss?: () => void
}

interface BackgroundJobContextValue {
  jobs: BackgroundJobItem[]
  addOrUpdateJob: (job: BackgroundJobItem) => void
  removeJob: (id: string) => void
  cancelJob: (id: string) => Promise<void>
  activeDownloadsCount: number
  activeTranscriptionsCount: number
  registerDownloadJob: (modelId: string, title?: string) => void
}

const BackgroundJobContext = createContext<BackgroundJobContextValue | undefined>(undefined)

/**
 * BackgroundJobProvider
 * Generic background job presentation coordinator for floating toasts and global counters.
 * Domain-specific stream/polling management (e.g. transcription SSE) is delegated
 * to feature providers (e.g. TranscriptionProvider).
 */
export const BackgroundJobProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { toast } = useToast()

  // Dynamic jobs collection in memory
  const [jobsMap, setJobsMap] = useState<Record<string, BackgroundJobItem>>({})
  const jobsMapRef = useRef(jobsMap)
  useEffect(() => {
    jobsMapRef.current = jobsMap
  }, [jobsMap])

  const dismissTimersRef = useRef<Record<string, number>>({})
  const dismissedJobsRef = useRef<Set<string>>(new Set())

  // 1. Helper to remove a job (manual dismiss or timer expiry)
  const removeJob = useCallback((id: string) => {
    dismissedJobsRef.current.add(id)
    if (dismissTimersRef.current[id]) {
      window.clearTimeout(dismissTimersRef.current[id])
      delete dismissTimersRef.current[id]
    }
    setJobsMap((prev) => {
      const copy = { ...prev }
      delete copy[id]
      return copy
    })
  }, [])

  // 2. Helper to add or update any job
  const addOrUpdateJob = useCallback(
    (job: BackgroundJobItem) => {
      const isTerminal = job.status === 'complete' || job.status === 'failed' || job.status === 'cancelled'

      // If user explicitly dismissed a job that is already terminal, don't resurrect it
      if (dismissedJobsRef.current.has(job.id) && isTerminal) {
        return
      }
      // If a job becomes active again, allow showing it
      if (!isTerminal && dismissedJobsRef.current.has(job.id)) {
        dismissedJobsRef.current.delete(job.id)
      }

      setJobsMap((prev) => ({
        ...prev,
        [job.id]: {
          ...(prev[job.id] || {}),
          ...job,
        },
      }))

      // Auto-dismiss terminal jobs after 4 seconds (or 3 seconds for cancelled)
      if (isTerminal) {
        if (!dismissTimersRef.current[job.id]) {
          const timeoutMs = job.status === 'cancelled' ? 3000 : 4000
          dismissTimersRef.current[job.id] = window.setTimeout(() => {
            removeJob(job.id)
            delete dismissTimersRef.current[job.id]
          }, timeoutMs)
        }
      } else {
        // If back to in-progress, clear any pending dismissal
        if (dismissTimersRef.current[job.id]) {
          window.clearTimeout(dismissTimersRef.current[job.id])
          delete dismissTimersRef.current[job.id]
        }
      }
    },
    [removeJob]
  )

  // 3. Cancel a job by ID
  const cancelJob = useCallback(
    async (id: string) => {
      const current = jobsMapRef.current[id]
      const isTranscription =
        current?.type === 'transcription' ||
        id.startsWith('trans_') ||
        (id.includes('-') && id.length >= 32)

      // Set cancelling state immediately for prompt visual feedback
      const cancellingText = isTranscription ? 'Cancelando transcripción...' : 'Cancelando descarga...'
      setJobsMap((prev) => {
        if (!prev[id]) return prev
        return {
          ...prev,
          [id]: {
            ...prev[id],
            stageText: cancellingText,
          },
        }
      })

      if (isTranscription) {
        try {
          await transcriptionApi.cancelTranscription(id)
          toast.info('Transcripción cancelada.')
        } catch (e) {
          console.warn(`Error al cancelar transcripción ${id}:`, e)
        }
      } else {
        try {
          await api.cancelBuiltinModelDownload(id)
          toast.info(`Descarga del modelo ${id} cancelada.`)
        } catch (e) {
          console.warn(`Error al cancelar descarga ${id}:`, e)
        }
      }

      // Mark final cancelled status in UI and reset progress
      const cancelledText = isTranscription ? 'Transcripción cancelada' : 'Descarga cancelada'
      addOrUpdateJob({
        id,
        type: current?.type || (isTranscription ? 'transcription' : 'download'),
        title: current?.title || (isTranscription ? 'Transcripción' : 'Descarga'),
        progress: 0,
        status: 'cancelled',
        stageText: cancelledText,
        eta: null,
      })
    },
    [addOrUpdateJob, toast]
  )

  // 4. Register a download job immediately
  const registerDownloadJob = useCallback(
    (modelId: string, title?: string) => {
      dismissedJobsRef.current.delete(modelId)
      if (dismissTimersRef.current[modelId]) {
        window.clearTimeout(dismissTimersRef.current[modelId])
        delete dismissTimersRef.current[modelId]
      }

      setJobsMap((prev) => {
        const copy = { ...prev }
        delete copy[modelId]

        return {
          ...copy,
          [modelId]: {
            id: modelId,
            type: 'download',
            title: title || `Descargando modelo ${modelId}`,
            progress: 0,
            status: 'uploading',
            stageText: 'Iniciando descarga en segundo plano...',
            speedOrSize: 'Iniciando...',
            onCancel: () => void cancelJob(modelId),
            onDismiss: () => removeJob(modelId),
          },
        }
      })
    },
    [cancelJob, removeJob]
  )

  // 5. Polling loop for active model downloads
  useEffect(() => {
    const pollInterval = window.setInterval(async () => {
      const hasActive = Object.values(jobsMapRef.current).some(
        (j) => j.type === 'download' && j.status !== 'complete' && j.status !== 'failed' && j.status !== 'cancelled'
      )
      if (!hasActive) return

      try {
        const res = await api.getBuiltinDownloadTasks()
        if (res.ok && Array.isArray(res.tasks)) {
          for (const t of res.tasks) {
            const current = jobsMapRef.current[t.id]
            const isComplete = t.status === 'complete'
            const isFailed = t.status === 'failed'
            const isCancelled = t.status === 'cancelled'

            // If locally cancelled by user, avoid reverting to uploading
            if (current?.status === 'cancelled' && t.status === 'downloading') {
              continue
            }

            const newStatus: BackgroundJobItem['status'] = isComplete
              ? 'complete'
              : isFailed
              ? 'failed'
              : isCancelled
              ? 'cancelled'
              : 'uploading'
            const newProgress = isComplete ? 100 : Math.max(0, t.progress)
            const newStageText = isCancelled
              ? 'Descarga cancelada por el usuario'
              : t.stageText || 'Descargando modelo...'
            const newSpeedOrSize = t.speedOrSize || current?.speedOrSize || null
            const newEta = isCancelled || isComplete ? null : t.eta

            if (
              !current ||
              current.progress !== newProgress ||
              current.status !== newStatus ||
              current.stageText !== newStageText ||
              current.speedOrSize !== newSpeedOrSize ||
              current.eta !== newEta
            ) {
              addOrUpdateJob({
                id: t.id,
                type: 'download',
                title: current?.title || t.title,
                progress: newProgress,
                status: newStatus,
                stageText: newStageText,
                speedOrSize: newSpeedOrSize,
                eta: newEta,
                onCancel: () => void cancelJob(t.id),
                onDismiss: () => removeJob(t.id),
              })
            }
          }
        }
      } catch {
        // silent polling catch
      }
    }, 500)

    return () => {
      window.clearInterval(pollInterval)
    }
  }, [addOrUpdateJob, cancelJob, removeJob])

  // Clean up all dismiss timers on unmount
  useEffect(() => {
    return () => {
      for (const timer of Object.values(dismissTimersRef.current)) {
        window.clearTimeout(timer)
      }
      dismissTimersRef.current = {}
    }
  }, [])

  // Derived memoized values
  const jobsList = useMemo(() => Object.values(jobsMap), [jobsMap])

  const activeDownloadsCount = useMemo(
    () =>
      jobsList.filter(
        (j) => j.type === 'download' && j.status !== 'complete' && j.status !== 'failed' && j.status !== 'cancelled'
      ).length,
    [jobsList]
  )

  const activeTranscriptionsCount = useMemo(
    () =>
      jobsList.filter(
        (j) =>
          j.type === 'transcription' &&
          j.status !== 'complete' &&
          j.status !== 'failed' &&
          j.status !== 'cancelled'
      ).length,
    [jobsList]
  )

  const contextValue = useMemo(
    () => ({
      jobs: jobsList,
      addOrUpdateJob,
      removeJob,
      cancelJob,
      activeDownloadsCount,
      activeTranscriptionsCount,
      registerDownloadJob,
    }),
    [
      jobsList,
      addOrUpdateJob,
      removeJob,
      cancelJob,
      activeDownloadsCount,
      activeTranscriptionsCount,
      registerDownloadJob,
    ]
  )

  return <BackgroundJobContext.Provider value={contextValue}>{children}</BackgroundJobContext.Provider>
}

export function useBackgroundJobs() {
  const context = useContext(BackgroundJobContext)
  if (!context) {
    throw new Error('useBackgroundJobs must be used within a BackgroundJobProvider')
  }
  return context
}
