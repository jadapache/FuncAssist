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
  const pollTimerRef = useRef<number | null>(null)

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
      const current = jobsMap[id]
      if (!current) return

      if (current.type === 'download') {
        try {
          await api.cancelBuiltinModelDownload(id)
          toast.info(`Cancelando descarga del modelo ${id}...`)
          setJobsMap((prev) => {
            if (!prev[id]) return prev
            return {
              ...prev,
              [id]: {
                ...prev[id],
                status: 'cancelled',
                stageText: 'Descarga cancelada por el usuario',
              },
            }
          })
        } catch (e) {
          console.warn(`Error al cancelar descarga ${id}:`, e)
        }
      } else if (current.type === 'transcription') {
        try {
          await transcriptionApi.cancelTranscription(id)
          toast.info('Cancelando transcripción...')
          setJobsMap((prev) => {
            if (!prev[id]) return prev
            return {
              ...prev,
              [id]: {
                ...prev[id],
                status: 'cancelled',
                stageText: 'Transcripción cancelada',
              },
            }
          })
          if (sseConnectionsRef.current[id]) {
            sseConnectionsRef.current[id].close()
            delete sseConnectionsRef.current[id]
          }
        } catch (e) {
          console.warn(`Error al cancelar transcripción ${id}:`, e)
        }
      }
    },
    [jobsMap, toast]
  )

  // 4. Register a download job immediately
  const registerDownloadJob = useCallback(
    (modelId: string, title?: string) => {
      addOrUpdateJob({
        id: modelId,
        type: 'download',
        title: title || `Descargando modelo ${modelId}`,
        progress: 1,
        status: 'uploading',
        stageText: 'Iniciando descarga en segundo plano...',
        speedOrSize: 'Iniciando...',
        onCancel: () => void cancelJob(modelId),
        onDismiss: () => removeJob(modelId),
      })
    },
    [addOrUpdateJob, cancelJob, removeJob]
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

  // 6. Polling loop for active model downloads
  useEffect(() => {
    const hasActiveDownloads = Object.values(jobsMap).some(
      (j) => j.type === 'download' && j.status !== 'complete' && j.status !== 'failed' && j.status !== 'cancelled'
    )

    if (!hasActiveDownloads) {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
      return
    }

    const pollDownloads = async () => {
      try {
        const res = await api.getBuiltinDownloadTasks()
        if (res.ok && Array.isArray(res.tasks)) {
          for (const t of res.tasks) {
            addOrUpdateJob({
              id: t.id,
              type: 'download',
              title: t.title,
              progress: t.progress,
              status: (t.status === 'downloading' ? 'uploading' : t.status) as any,
              stageText: t.stageText || 'Descargando modelo GGUF...',
              speedOrSize: t.speedOrSize,
              eta: t.eta,
              onCancel: () => void cancelJob(t.id),
              onDismiss: () => removeJob(t.id),
            })
          }
        }
      } catch {
        // silent polling catch
      }
    }

    pollTimerRef.current = window.setInterval(() => {
      void pollDownloads()
    }, 800)
    void pollDownloads()

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [addOrUpdateJob, cancelJob, jobsMap, removeJob])

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
