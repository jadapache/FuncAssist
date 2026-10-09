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
import {
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionProgress,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'
import { useBackgroundJobs } from '../../../context/BackgroundJobContext'

const LOCAL_STORAGE_ACTIVE_JOBS = 'qa_active_transcription_jobs'

export const STAGE_TRANSLATIONS: Record<string, string> = {
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

export const getTranscriptionStageText = (data: {
  stage?: string
  status?: string
  message?: string
  error?: string | null
}): string => {
  const isComplete = data.stage === 'complete' || data.status === 'complete'
  const isFailed = data.stage === 'failed' || data.status === 'failed'
  const isCancelled = data.stage === 'cancelled' || data.status === 'cancelled'

  if (isComplete) return 'Completado'
  if (isCancelled) return 'Transcripción cancelada'
  if (isFailed) return data.error || data.message || 'Error en procesamiento'
  if (data.message) return data.message
  if (data.stage && STAGE_TRANSLATIONS[data.stage.toLowerCase()]) {
    return STAGE_TRANSLATIONS[data.stage.toLowerCase()]
  }
  return 'Procesando audio...'
}

export interface TranscriptionContextValue {
  viewMode: 'dashboard' | 'studio'
  setViewMode: React.Dispatch<React.SetStateAction<'dashboard' | 'studio'>>
  openStudio: (transcriptionId: string) => void
  closeStudio: () => void
  activeJobs: TranscriptionProgress[]
  recentTranscriptions: TranscriptionResult[]
  availableModels: AvailableModelsInfo | null
  isLoadingList: boolean
  isUploading: boolean
  showProgressModal: boolean
  showSummaryModal: boolean
  showGenerateModal: boolean
  selectedTranscriptionId: string | null
  activeMeetingTitle: string
  currentProgress: TranscriptionProgress | null
  handleUploadAndStart: (file: any, title: string, description?: string) => Promise<void>
  handleRetranscribe: (transcriptionId: string, title?: string) => Promise<void>
  handleCancelTranscription: (transcriptionId: string) => Promise<void>
  handleDeleteTranscription: (transcriptionId: string) => Promise<void>
  handleDismissJob: (id: string) => void
  openProgressModal: (transcriptionId: string) => void
  openSummaryModal: (transcriptionId: string) => void
  openGenerateModal: (transcriptionId: string) => void
  closeAllModals: () => void
  setShowProgressModal: React.Dispatch<React.SetStateAction<boolean>>
  setShowSummaryModal: React.Dispatch<React.SetStateAction<boolean>>
  setShowGenerateModal: React.Dispatch<React.SetStateAction<boolean>>
  refreshTranscriptions: () => Promise<void>
}

const TranscriptionContext = createContext<TranscriptionContextValue | undefined>(undefined)

export const TranscriptionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { toast } = useToast()
  const navigate = useNavigate()
  const { addOrUpdateJob, removeJob, cancelJob } = useBackgroundJobs()

  // View mode
  const [viewMode, setViewMode] = useState<'dashboard' | 'studio'>('dashboard')

  // Data lists
  const [activeJobs, setActiveJobs] = useState<Record<string, TranscriptionProgress>>({})
  const activeJobsRef = useRef(activeJobs)
  useEffect(() => {
    activeJobsRef.current = activeJobs
  }, [activeJobs])

  const [recentTranscriptions, setRecentTranscriptions] = useState<TranscriptionResult[]>([])
  const [availableModels, setAvailableModels] = useState<AvailableModelsInfo | null>(null)
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [isUploading, setIsUploading] = useState(false)

  // Modals state
  const [showProgressModal, setShowProgressModal] = useState(false)
  const [showSummaryModal, setShowSummaryModal] = useState(false)
  const [showGenerateModal, setShowGenerateModal] = useState(false)
  const [selectedTranscriptionId, setSelectedTranscriptionId] = useState<string | null>(null)
  const [activeMeetingTitle, setActiveMeetingTitle] = useState<string>('')

  const pollingTimerRef = useRef<number | null>(null)
  const eventSourcesRef = useRef<Record<string, EventSource>>({})
  const abortControllersRef = useRef<Record<string, AbortController>>({})
  const cancelledJobsRef = useRef<Set<string>>(new Set())

  // Navigation helpers
  const openStudio = useCallback((transcriptionId: string) => {
    setSelectedTranscriptionId(transcriptionId)
    const active = activeJobsRef.current[transcriptionId]
    if (active?.title) {
      setActiveMeetingTitle(active.title)
    }
    setViewMode('studio')
  }, [])

  const closeStudio = useCallback(() => {
    setViewMode('dashboard')
  }, [])

  const handleDismissJob = useCallback((id: string) => {
    cancelledJobsRef.current.delete(id)
    if (abortControllersRef.current[id]) {
      abortControllersRef.current[id].abort()
      delete abortControllersRef.current[id]
    }
    if (eventSourcesRef.current[id]) {
      eventSourcesRef.current[id].close()
      delete eventSourcesRef.current[id]
    }
    setActiveJobs((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    removeJob(id)
  }, [removeJob])

  // Synchronize active jobs with localStorage
  const saveActiveJobsToStorage = useCallback((jobs: Record<string, TranscriptionProgress>) => {
    try {
      const activeOnly: Record<string, TranscriptionProgress> = {}
      for (const [id, job] of Object.entries(jobs)) {
        if (
          !id.startsWith('upload_') &&
          job.status !== 'complete' &&
          job.status !== 'failed' &&
          job.status !== 'cancelled'
        ) {
          activeOnly[id] = job
        }
      }
      localStorage.setItem(LOCAL_STORAGE_ACTIVE_JOBS, JSON.stringify(activeOnly))
    } catch (e) {
      console.warn('Could not persist active jobs to localStorage:', e)
    }
  }, [])

  // Fetch recent saved transcriptions
  const refreshTranscriptions = useCallback(async () => {
    try {
      setIsLoadingList(true)
      const res = await transcriptionApi.listTranscriptions()
      setRecentTranscriptions(res.transcriptions || [])
    } catch (err: any) {
      console.warn('Error fetching transcriptions list:', err)
    } finally {
      setIsLoadingList(false)
    }
  }, [])

  // Cancel transcription
  const handleCancelTranscription = useCallback(
    async (transcriptionId: string) => {
      try {
        cancelledJobsRef.current.add(transcriptionId)

        // Abort in-flight upload XHR immediately
        if (abortControllersRef.current[transcriptionId]) {
          abortControllersRef.current[transcriptionId].abort()
          delete abortControllersRef.current[transcriptionId]
        }

        // Close SSE stream immediately
        if (eventSourcesRef.current[transcriptionId]) {
          eventSourcesRef.current[transcriptionId].close()
          delete eventSourcesRef.current[transcriptionId]
        }

        // Remove from local active jobs map immediately
        setActiveJobs((prev) => {
          const next = { ...prev }
          delete next[transcriptionId]
          return next
        })

        if (selectedTranscriptionId === transcriptionId && viewMode === 'studio') {
          setViewMode('dashboard')
        }
        setShowProgressModal(false)

        await cancelJob(transcriptionId)
        await refreshTranscriptions()
      } catch (err: any) {
        console.warn('Error cancelling transcription:', err)
      }
    },
    [cancelJob, refreshTranscriptions, selectedTranscriptionId, viewMode]
  )

  // Fetch available models and restore persisted jobs on mount
  useEffect(() => {
    transcriptionApi
      .getAvailableModels()
      .then(setAvailableModels)
      .catch((e) => console.warn('Could not load models info:', e))

    refreshTranscriptions()

    // Restore jobs from localStorage (filtering out stale upload_ and terminal jobs)
    try {
      const stored = localStorage.getItem(LOCAL_STORAGE_ACTIVE_JOBS)
      if (stored) {
        const parsed: Record<string, TranscriptionProgress> = JSON.parse(stored)
        const validJobs: Record<string, TranscriptionProgress> = {}
        for (const [id, job] of Object.entries(parsed)) {
          if (
            !id.startsWith('upload_') &&
            job.status !== 'complete' &&
            job.status !== 'failed' &&
            job.status !== 'cancelled'
          ) {
            validJobs[id] = job
          }
        }
        if (Object.keys(validJobs).length > 0) {
          setActiveJobs(validJobs)
          for (const [id, job] of Object.entries(validJobs)) {
            const title = job.title || 'Transcripción'
            addOrUpdateJob({
              id,
              type: 'transcription',
              title,
              progress: typeof job.progress === 'number' ? job.progress : 0,
              status: job.status,
              stageText: getTranscriptionStageText(job),
              speedOrSize: job.preview || null,
              eta: job.eta || null,
              onClick: () => {
                openStudio(id)
                navigate('/funcional/transcripciones')
              },
              onCancel: () => void handleCancelTranscription(id),
              onDismiss: () => handleDismissJob(id),
            })
          }
        }
      }
    } catch (e) {
      console.warn('Error reading active jobs from storage:', e)
    }
  }, [addOrUpdateJob, handleCancelTranscription, handleDismissJob, navigate, openStudio, refreshTranscriptions])

  // Save active jobs changes to localStorage
  useEffect(() => {
    saveActiveJobsToStorage(activeJobs)
  }, [activeJobs, saveActiveJobsToStorage])

  // Compute active job IDs key for dependency tracking (only changes when jobs are added/finished)
  const activeIdsKey = useMemo(() => {
    return Object.keys(activeJobs)
      .filter(
        (id) =>
          !id.startsWith('upload_') &&
          activeJobs[id].status !== 'complete' &&
          activeJobs[id].status !== 'failed' &&
          activeJobs[id].status !== 'cancelled' &&
          activeJobs[id].status !== 'uploading'
      )
      .sort()
      .join(',')
  }, [activeJobs])

  // Manage SINGLE SSE connection and SINGLE fallback polling loop per active job
  useEffect(() => {
    const activeIds = activeIdsKey ? activeIdsKey.split(',') : []

    // 1. Open EventSource for each active job if not already opened
    for (const id of activeIds) {
      if (!eventSourcesRef.current[id]) {
        try {
          const streamUrl = transcriptionApi.getProgressStreamUrl(id)
          const es = new EventSource(streamUrl)
          eventSourcesRef.current[id] = es

          es.addEventListener('message', async (event) => {
            try {
              if (cancelledJobsRef.current.has(id)) {
                es.close()
                delete eventSourcesRef.current[id]
                return
              }

              const data = JSON.parse(event.data)
              if (data.stage === 'heartbeat' || data.event === 'heartbeat' || data.event === 'connected') {
                return
              }

              const isCancelled = data.stage === 'cancelled' || data.status === 'cancelled'
              if (isCancelled) {
                cancelledJobsRef.current.add(id)
                es.close()
                delete eventSourcesRef.current[id]
                setActiveJobs((prev) => {
                  const next = { ...prev }
                  delete next[id]
                  return next
                })
                addOrUpdateJob({
                  id,
                  type: 'transcription',
                  title: data.title || activeJobsRef.current[id]?.title || 'Transcripción',
                  progress: 0,
                  status: 'cancelled',
                  stageText: 'Transcripción cancelada',
                  eta: null,
                })
                return
              }

              const updatedProgress = typeof data.progress === 'number' ? data.progress : 0
              const isDone = data.stage === 'complete' || updatedProgress === 100
              const isFail = data.stage === 'failed'
              const updatedStatus: TranscriptionProgress['status'] = isDone
                ? 'complete'
                : isFail
                  ? 'failed'
                  : 'transcribing'
              const stageText = getTranscriptionStageText(data)

              setActiveJobs((prev) => {
                if (cancelledJobsRef.current.has(id)) return prev
                const existing = prev[id]
                const finalProgress = typeof data.progress === 'number' ? data.progress : existing?.progress || 0
                return {
                  ...prev,
                  [id]: {
                    id,
                    media_id: existing?.media_id || data.media_id || '',
                    title: data.title || existing?.title,
                    status: updatedStatus,
                    stage: data.stage || existing?.stage,
                    progress: isDone ? 100 : finalProgress,
                    message: stageText,
                    preview: data.preview,
                    eta: isDone || isFail ? null : data.eta || existing?.eta,
                    model_info: data.model_info || existing?.model_info,
                    error: data.error,
                  },
                }
              })

              addOrUpdateJob({
                id,
                type: 'transcription',
                title: data.title || activeJobsRef.current[id]?.title || 'Transcripción',
                progress: isDone ? 100 : updatedProgress,
                status: updatedStatus,
                stageText,
                speedOrSize: data.preview || null,
                eta: isDone || isFail ? null : data.eta || null,
                onClick: () => {
                  openStudio(id)
                  navigate('/funcional/transcripciones')
                },
                onCancel: () => void handleCancelTranscription(id),
                onDismiss: () => handleDismissJob(id),
              })

              if (isDone || isFail) {
                es.close()
                delete eventSourcesRef.current[id]
                if (isDone) {
                  await refreshTranscriptions()
                }
              }
            } catch (err) {
              console.warn('Error parsing SSE in TranscriptionContext:', err)
            }
          })

          es.onerror = () => {
            if (es.readyState === EventSource.CLOSED) {
              es.close()
              delete eventSourcesRef.current[id]
            }
          }
        } catch (e) {
          console.warn('Could not start EventSource for job:', id, e)
        }
      }
    }

    // 2. Clean up closed EventSources for non-active jobs
    for (const id of Object.keys(eventSourcesRef.current)) {
      if (!activeIds.includes(id)) {
        eventSourcesRef.current[id]?.close()
        delete eventSourcesRef.current[id]
      }
    }

    // 3. Fallback polling loop (every 2.5s) if there are active jobs
    if (activeIds.length > 0 && !pollingTimerRef.current) {
      pollingTimerRef.current = window.setInterval(async () => {
        const currentActive = Object.keys(activeJobsRef.current).filter(
          (id) =>
            !id.startsWith('upload_') &&
            activeJobsRef.current[id].status !== 'complete' &&
            activeJobsRef.current[id].status !== 'failed' &&
            activeJobsRef.current[id].status !== 'cancelled' &&
            activeJobsRef.current[id].status !== 'uploading'
        )

        if (currentActive.length === 0) {
          if (pollingTimerRef.current) {
            clearInterval(pollingTimerRef.current)
            pollingTimerRef.current = null
          }
          return
        }

        for (const id of currentActive) {
          if (cancelledJobsRef.current.has(id)) continue
          try {
            const status = await transcriptionApi.getTranscriptionStatus(id)
            if (!status || cancelledJobsRef.current.has(id)) continue

            const isCancelled = status.status === 'cancelled' || status.stage === 'cancelled'
            if (isCancelled) {
              cancelledJobsRef.current.add(id)
              if (eventSourcesRef.current[id]) {
                eventSourcesRef.current[id].close()
                delete eventSourcesRef.current[id]
              }
              setActiveJobs((prev) => {
                const next = { ...prev }
                delete next[id]
                return next
              })
              addOrUpdateJob({
                id,
                type: 'transcription',
                title: status.title || activeJobsRef.current[id]?.title || 'Transcripción',
                progress: 0,
                status: 'cancelled',
                stageText: 'Transcripción cancelada',
                eta: null,
              })
              continue
            }

            const isDone = status.status === 'complete' || status.progress === 100
            const isFail = status.status === 'failed'
            const finalStatus: TranscriptionProgress['status'] = isDone
              ? 'complete'
              : isFail
                ? 'failed'
                : (status.status as any) || 'transcribing'
            const finalProgress = isDone ? 100 : typeof status.progress === 'number' ? status.progress : 0
            const stageText = getTranscriptionStageText(status)

            setActiveJobs((prev) => {
              if (cancelledJobsRef.current.has(id)) return prev
              const prevJob = prev[id]
              return {
                ...prev,
                [id]: {
                  ...(prevJob || {}),
                  ...status,
                  status: finalStatus,
                  progress: finalProgress,
                  message: stageText,
                },
              }
            })

            addOrUpdateJob({
              id,
              type: 'transcription',
              title: status.title || activeJobsRef.current[id]?.title || 'Transcripción',
              progress: finalProgress,
              status: finalStatus,
              stageText,
              speedOrSize: status.preview || null,
              eta: isDone || isFail ? null : status.eta || null,
              onClick: () => {
                openStudio(id)
                navigate('/funcional/transcripciones')
              },
              onCancel: () => void handleCancelTranscription(id),
              onDismiss: () => handleDismissJob(id),
            })

            if (isDone || isFail) {
              if (eventSourcesRef.current[id]) {
                eventSourcesRef.current[id].close()
                delete eventSourcesRef.current[id]
              }
              if (isDone) {
                await refreshTranscriptions()
              }
            }
          } catch {
            // silent catch in polling loop
          }
        }
      }, 2500)
    } else if (activeIds.length === 0 && pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current)
      pollingTimerRef.current = null
    }
  }, [
    activeIdsKey,
    addOrUpdateJob,
    handleCancelTranscription,
    handleDismissJob,
    navigate,
    openStudio,
    refreshTranscriptions,
  ])

  // Clean up all EventSources and timers on unmount
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current)
        pollingTimerRef.current = null
      }
      for (const controller of Object.values(abortControllersRef.current)) {
        controller.abort()
      }
      abortControllersRef.current = {}
      for (const es of Object.values(eventSourcesRef.current)) {
        es?.close()
      }
      eventSourcesRef.current = {}
    }
  }, [])

  // Start upload and transcription pipeline -> auto-transition to Studio
  const handleUploadAndStart = async (target: any, title: string, description: string = '') => {
    const transcriptionId =
      typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `trans_${Date.now()}`

    cancelledJobsRef.current.delete(transcriptionId)
    const abortController = new AbortController()
    abortControllersRef.current[transcriptionId] = abortController

    const targetName = (target && typeof target === 'object' && ('name' in target ? target.name : target.filename)) || 'archivo_multimedia'
    const localPath = ((target as any)?.path || (target as any)?.filePath || '') as string

    try {
      setIsUploading(true)
      setActiveMeetingTitle(title)

      let mediaId = transcriptionId

      if (localPath && typeof localPath === 'string' && localPath.trim().length > 0) {
        // Zero-copy directo: vincular la ruta local existente en disco sin transferir gigabytes por HTTP
        const regRes = await transcriptionApi.registerLocalPath(
          localPath.trim(),
          title,
          description,
          transcriptionId
        )
        mediaId = regRes.media_id || transcriptionId
      } else if (target && typeof (target as any).size === 'number') {
        // Fallback para navegador web estándar: subir el archivo por streaming HTTP
        const initialUploadJob: TranscriptionProgress = {
          id: transcriptionId,
          media_id: '',
          title,
          status: 'uploading',
          stage: 'uploading',
          progress: 1,
          message: `Iniciando subida de "${targetName}"...`,
          model_info: availableModels?.active_model_label || 'Whisper Auto',
        }
        setActiveJobs((prev) => ({
          ...prev,
          [transcriptionId]: initialUploadJob,
        }))
        addOrUpdateJob({
          id: transcriptionId,
          type: 'transcription',
          title,
          progress: 1,
          status: 'uploading',
          stageText: `Iniciando subida de "${targetName}"...`,
          onClick: () => {
            openStudio(transcriptionId)
            navigate('/funcional/transcripciones')
          },
          onCancel: () => void handleCancelTranscription(transcriptionId),
          onDismiss: () => handleDismissJob(transcriptionId),
        })

        const uploadRes = await transcriptionApi.uploadMediaWithProgress(
          target as File,
          title,
          description,
          (prog, msg) => {
            if (cancelledJobsRef.current.has(transcriptionId)) return
            const calculatedProgress = Math.min(10, Math.max(1, Math.round(prog / 10)))
            setActiveJobs((prev) => {
              if (!prev[transcriptionId] || cancelledJobsRef.current.has(transcriptionId)) return prev
              return {
                ...prev,
                [transcriptionId]: {
                  ...prev[transcriptionId],
                  progress: calculatedProgress,
                  message: msg,
                },
              }
            })
            addOrUpdateJob({
              id: transcriptionId,
              type: 'transcription',
              title,
              progress: calculatedProgress,
              status: 'uploading',
              stageText: msg,
              onClick: () => {
                openStudio(transcriptionId)
                navigate('/funcional/transcripciones')
              },
              onCancel: () => void handleCancelTranscription(transcriptionId),
              onDismiss: () => handleDismissJob(transcriptionId),
            })
          },
          transcriptionId,
          abortController.signal
        )
        mediaId = uploadRes.media_id || transcriptionId
      }

      delete abortControllersRef.current[transcriptionId]
      if (cancelledJobsRef.current.has(transcriptionId)) return

      // Transición a preprocesamiento con el mismo ID
      const preprocessingJob: TranscriptionProgress = {
        id: transcriptionId,
        media_id: mediaId,
        title,
        status: 'preprocessing',
        stage: 'preprocessing',
        progress: 15,
        message: 'Archivo cargado. Iniciando transcripción...',
        eta: '~45 s',
        model_info: availableModels?.active_model_label || 'Whisper Auto',
      }
      setActiveJobs((prev) => {
        if (cancelledJobsRef.current.has(transcriptionId)) return prev
        return {
          ...prev,
          [transcriptionId]: preprocessingJob,
        }
      })
      addOrUpdateJob({
        id: transcriptionId,
        type: 'transcription',
        title,
        progress: 15,
        status: 'preprocessing',
        stageText: 'Archivo cargado. Iniciando transcripción...',
        eta: '~45 s',
        onClick: () => {
          openStudio(transcriptionId)
          navigate('/funcional/transcripciones')
        },
        onCancel: () => void handleCancelTranscription(transcriptionId),
        onDismiss: () => handleDismissJob(transcriptionId),
      })

      setSelectedTranscriptionId(transcriptionId)

      if (cancelledJobsRef.current.has(transcriptionId)) return

      // Iniciar transcripción en el backend
      await transcriptionApi.startTranscription(mediaId, {
        transcription_id: transcriptionId,
        mode: 'auto',
        enable_diarization: true,
      })

      // Transición inmediata a Transcription Studio
      if (!cancelledJobsRef.current.has(transcriptionId)) {
        setViewMode('studio')
      }
    } catch (err: any) {
      delete abortControllersRef.current[transcriptionId]
      if (cancelledJobsRef.current.has(transcriptionId)) {
        // Cancelación solicitada por el usuario
        return
      }
      setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })
      removeJob(transcriptionId)
      throw err
    } finally {
      setIsUploading(false)
    }
  }

  // Delete saved transcription
  const handleDeleteTranscription = async (transcriptionId: string) => {
    try {
      await transcriptionApi.deleteTranscription(transcriptionId)
      setRecentTranscriptions((prev) => prev.filter((t) => t.id !== transcriptionId))
      setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })
      removeJob(transcriptionId)
      if (selectedTranscriptionId === transcriptionId) {
        setViewMode('dashboard')
        setSelectedTranscriptionId(null)
      }
      toast.success('Transcripción eliminada con éxito.')
    } catch (err: any) {
      toast.error(`Error al eliminar: ${err.message}`)
    }
  }

  // Retranscribe with current configured model
  const handleRetranscribe = async (transcriptionId: string, title?: string) => {
    try {
      const active = activeJobs[transcriptionId]
      const recent = recentTranscriptions.find((t) => t.id === transcriptionId)
      const jobTitle = title || active?.title || recent?.metadata?.title || activeMeetingTitle || 'Transcripción'

      const retransJob: TranscriptionProgress = {
        id: transcriptionId,
        media_id: recent?.media_id || '',
        title: jobTitle,
        status: 'preprocessing',
        stage: 'preprocessing',
        progress: 15,
        message: 'Iniciando regeneración con el motor configurado...',
        eta: '~45 s',
        model_info: availableModels?.active_model_label || 'Whisper Auto',
      }
      setActiveJobs((prev) => ({
        ...prev,
        [transcriptionId]: retransJob,
      }))
      addOrUpdateJob({
        id: transcriptionId,
        type: 'transcription',
        title: jobTitle,
        progress: 15,
        status: 'preprocessing',
        stageText: 'Iniciando regeneración con el motor configurado...',
        eta: '~45 s',
        onClick: () => {
          openStudio(transcriptionId)
          navigate('/funcional/transcripciones')
        },
        onCancel: () => void handleCancelTranscription(transcriptionId),
        onDismiss: () => handleDismissJob(transcriptionId),
      })

      await transcriptionApi.retranscribe(transcriptionId, {
        mode: 'auto',
        enable_diarization: true,
      })
      toast.info('Regeneración de transcripción iniciada.')
    } catch (err: any) {
      toast.error(`Error al regenerar transcripción: ${err.message}`)
      setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })
      removeJob(transcriptionId)
    }
  }

  const openProgressModal = (transcriptionId: string) => {
    openStudio(transcriptionId)
  }

  const openSummaryModal = (transcriptionId: string) => {
    openStudio(transcriptionId)
  }

  const openGenerateModal = (transcriptionId: string) => {
    setSelectedTranscriptionId(transcriptionId)
    const recent = recentTranscriptions.find((t) => t.id === transcriptionId)
    if (recent) {
      setActiveMeetingTitle(recent.metadata.title)
    }
    setShowGenerateModal(true)
  }

  const closeAllModals = () => {
    setShowProgressModal(false)
    setShowSummaryModal(false)
    setShowGenerateModal(false)
  }

  // Active progress for selected transcription
  const currentProgress = selectedTranscriptionId ? activeJobs[selectedTranscriptionId] || null : null

  const value: TranscriptionContextValue = {
    viewMode,
    setViewMode,
    openStudio,
    closeStudio,
    activeJobs: Object.values(activeJobs),
    recentTranscriptions,
    availableModels,
    isLoadingList,
    isUploading,
    showProgressModal,
    showSummaryModal,
    showGenerateModal,
    selectedTranscriptionId,
    activeMeetingTitle,
    currentProgress,
    handleUploadAndStart,
    handleRetranscribe,
    handleCancelTranscription,
    handleDeleteTranscription,
    handleDismissJob,
    openProgressModal,
    openSummaryModal,
    openGenerateModal,
    closeAllModals,
    setShowProgressModal,
    setShowSummaryModal,
    setShowGenerateModal,
    refreshTranscriptions,
  }

  return <TranscriptionContext.Provider value={value}>{children}</TranscriptionContext.Provider>
}

export function useTranscription() {
  const context = useContext(TranscriptionContext)
  if (!context) {
    throw new Error('useTranscription must be used within a TranscriptionProvider')
  }
  return context
}
