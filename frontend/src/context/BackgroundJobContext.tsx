import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { transcriptionApi, type TranscriptionProgress } from '../features/transcription/api/transcriptionApi'
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

const LOCAL_STORAGE_ACTIVE_TRANSCRIPTIONS = 'qa_active_transcription_jobs'

const STAGE_TRANSLATIONS: Record<string, string> = {
  pending: 'En cola...',
  uploading: 'Subiendo archivo...',
  preprocessing: 'Extrayendo audio...',
  transcribing: 'Transcribiendo...',
  diarizing: 'Identificando interlocutores...',
  summarizing: 'Generando resumen...',
  finalizing: 'Finalizando...',
  complete: 'Completado',
  failed: 'Error',
  cancelled: 'Cancelado',
}

export const BackgroundJobProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { toast } = useToast()
  const navigate = useNavigate()

  // Dynamic jobs collection in memory
  const [jobsMap, setJobsMap] = useState<Record<string, BackgroundJobItem>>({})
  const sseConnectionsRef = useRef<Record<string, EventSource>>({})

  const dismissTimersRef = useRef<Record<string, number>>({})

  // 1. Helper to add or update any job
  const addOrUpdateJob = useCallback((job: BackgroundJobItem) => {
    setJobsMap((prev) => ({
      ...prev,
      [job.id]: {
        ...(prev[job.id] || {}),
        ...job,
      },
    }))
  }, [])

  // 2. Helper to remove a job (dismiss)
  const removeJob = useCallback((id: string) => {
    if (dismissTimersRef.current[id]) {
      window.clearTimeout(dismissTimersRef.current[id])
      delete dismissTimersRef.current[id]
    }
    setJobsMap((prev) => {
      const copy = { ...prev }
      delete copy[id]
      return copy
    })
    if (sseConnectionsRef.current[id]) {
      sseConnectionsRef.current[id].close()
      delete sseConnectionsRef.current[id]
    }
  }, [])

  // 3. Cancel a job by ID
  const cancelJob = useCallback(
    async (id: string) => {
      const current = jobsMapRef.current[id]

      // Set cancelled status immediately in UI and reset progress
      setJobsMap((prev) => {
        if (!prev[id]) return prev
        return {
          ...prev,
          [id]: {
            ...prev[id],
            progress: 0,
            status: 'cancelled',
            stageText: 'Descarga cancelada por el usuario',
          },
        }
      })

      if (current?.type === 'download' || !current) {
        try {
          await api.cancelBuiltinModelDownload(id)
          toast.info(`Descarga del modelo ${id} cancelada.`)
        } catch (e) {
          console.warn(`Error al cancelar descarga ${id}:`, e)
        }
      } else if (current?.type === 'transcription') {
        try {
          await transcriptionApi.cancelTranscription(id)
          toast.info('Transcripción cancelada.')
          if (sseConnectionsRef.current[id]) {
            sseConnectionsRef.current[id].close()
            delete sseConnectionsRef.current[id]
          }
        } catch (e) {
          console.warn(`Error al cancelar transcripción ${id}:`, e)
        }
      }

      // Auto-remove cancelled job card after 3 seconds if not dismissed manually
      if (dismissTimersRef.current[id]) {
        window.clearTimeout(dismissTimersRef.current[id])
      }
      dismissTimersRef.current[id] = window.setTimeout(() => {
        removeJob(id)
        delete dismissTimersRef.current[id]
      }, 3000)
    },
    [removeJob, toast]
  )

  // 4. Register a download job immediately
  const registerDownloadJob = useCallback(
    (modelId: string, title?: string) => {
      // Clear any pending dismissal timeout
      if (dismissTimersRef.current[modelId]) {
        window.clearTimeout(dismissTimersRef.current[modelId])
        delete dismissTimersRef.current[modelId]
      }
      // **COMPLETELY RESET** the job - remove any stale state (cancelled, failed, etc.)
      // This ensures a fresh start when retrying a download
      setJobsMap((prev) => {
        // Remove the old entry completely first
        const copy = { ...prev }
        delete copy[modelId]
        
        // Then add fresh job
        return {
          ...copy,
          [modelId]: {
            id: modelId,
            type: 'download',
            title: title || `Descargando modelo ${modelId}`,
            progress: 1,
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

  // 5. Restore active transcription jobs from localStorage on first mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(LOCAL_STORAGE_ACTIVE_TRANSCRIPTIONS)
      if (stored) {
        const parsed: Record<string, TranscriptionProgress> = JSON.parse(stored)
        for (const [id, job] of Object.entries(parsed)) {
          if (job.status !== 'complete' && job.status !== 'failed' && job.status !== 'cancelled') {
            const title = job.title || (job.model_info ? `Transcribir (${job.model_info})` : 'Transcribir Audio')
            addOrUpdateJob({
              id,
              type: 'transcription',
              title,
              progress: typeof job.progress === 'number' ? job.progress : 0,
              status: job.status,
              stageText: STAGE_TRANSLATIONS[job.stage || job.status] || job.message || 'Procesando...',
              eta: job.eta,
              speedOrSize: job.preview || null,
              onCancel: () => void cancelJob(id),
              onClick: () => navigate('/funcional/transcripciones'),
              onDismiss: () => removeJob(id),
            })
          }
        }
      }
    } catch (e) {
      console.warn('Error reading stored transcription jobs:', e)
    }
  }, [addOrUpdateJob, cancelJob, navigate, removeJob])

  const jobsMapRef = useRef(jobsMap)
  jobsMapRef.current = jobsMap

  // 6. Polling loop for active model downloads
  useEffect(() => {
    const pollInterval = window.setInterval(async () => {
      const hasActive = Object.values(jobsMapRef.current).some(
        (j) => j.type === 'download' && j.status !== 'complete' && j.status !== 'failed' && j.status !== 'cancelled'
      )
      if (!hasActive) return

      try {
        const res = await api.getBuiltinDownloadTasks()
        if (res.ok && Array.isArray(res.tasks)) {
          setJobsMap((prev) => {
            const next = { ...prev }
            let hasChanges = false

            for (const t of res.tasks) {
              const current = prev[t.id]
              // If local job was cancelled by user, avoid reverting to uploading
              if (current?.status === 'cancelled' && t.status === 'downloading') {
                continue
              }

              const isComplete = t.status === 'complete'
              const isFailed = t.status === 'failed'
              const isCancelled = t.status === 'cancelled'

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
                next[t.id] = {
                  ...(current || {}),
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
                }
                hasChanges = true
              }
            }

            return hasChanges ? next : prev
          })
        }
      } catch {
        // silent polling catch
      }
    }, 500)

    return () => {
      window.clearInterval(pollInterval)
    }
  }, [cancelJob, removeJob])

  // 7. SSE management for active transcriptions
  useEffect(() => {
    const activeTranscriptions = Object.values(jobsMap).filter(
      (j) =>
        j.type === 'transcription' &&
        j.status !== 'complete' &&
        j.status !== 'failed' &&
        j.status !== 'cancelled' &&
        !j.id.startsWith('upload_')
    )

    for (const job of activeTranscriptions) {
      const id = job.id
      if (!sseConnectionsRef.current[id]) {
        try {
          const streamUrl = transcriptionApi.getProgressStreamUrl(id)
          const es = new EventSource(streamUrl)
          sseConnectionsRef.current[id] = es

          es.addEventListener('message', (event) => {
            try {
              const data = JSON.parse(event.data)
              if (data.stage === 'heartbeat' || data.event === 'heartbeat' || data.event === 'connected') {
                return
              }

              const isComplete = data.stage === 'complete' || data.progress === 100
              const isFailed = data.stage === 'failed'

              let stageText = 'Procesando...'
              if (isComplete) stageText = 'Completado'
              else if (isFailed) stageText = data.error || data.message || 'Error en procesamiento'
              else if (data.stage && STAGE_TRANSLATIONS[data.stage.toLowerCase()]) {
                stageText = STAGE_TRANSLATIONS[data.stage.toLowerCase()]
              } else if (data.message) stageText = data.message

              addOrUpdateJob({
                id,
                type: 'transcription',
                title: data.title || job.title,
                progress: typeof data.progress === 'number' ? data.progress : job.progress,
                status: isComplete ? 'complete' : isFailed ? 'failed' : 'transcribing',
                stageText,
                speedOrSize: data.preview || job.speedOrSize,
                eta: data.eta || job.eta,
                onCancel: () => void cancelJob(id),
                onClick: () => navigate('/funcional/transcripciones'),
                onDismiss: () => removeJob(id),
              })

              if (isComplete || isFailed) {
                es.close()
                delete sseConnectionsRef.current[id]
              }
            } catch (err) {
              console.warn('Error parsing SSE in BackgroundJobProvider:', err)
            }
          })

          es.addEventListener('error', () => {
            // keep connection attempt
          })
        } catch (e) {
          console.warn('Could not start EventSource for job:', id, e)
        }
      }
    }
  }, [addOrUpdateJob, cancelJob, jobsMap, navigate, removeJob])

  // 8. Sync active transcriptions to localStorage
  useEffect(() => {
    try {
      const activeTranscriptions: Record<string, any> = {}
      for (const [id, job] of Object.entries(jobsMap)) {
        if (
          job.type === 'transcription' &&
          job.status !== 'complete' &&
          job.status !== 'failed' &&
          job.status !== 'cancelled'
        ) {
          activeTranscriptions[id] = {
            id: job.id,
            title: job.title,
            progress: job.progress,
            status: job.status,
            stage: job.status,
            message: job.stageText,
            preview: job.speedOrSize,
            eta: job.eta,
          }
        }
      }
      localStorage.setItem(LOCAL_STORAGE_ACTIVE_TRANSCRIPTIONS, JSON.stringify(activeTranscriptions))
    } catch {
      // storage quota or serialization error fallback
    }
  }, [jobsMap])

  // Counts
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
    [jobsList, addOrUpdateJob, removeJob, cancelJob, activeDownloadsCount, activeTranscriptionsCount, registerDownloadJob]
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
