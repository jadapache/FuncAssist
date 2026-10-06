import { useState, useEffect, useRef, useCallback } from 'react'
import {
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionProgress,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'
import { useBackgroundJobs } from '../../../context/BackgroundJobContext'

const LOCAL_STORAGE_ACTIVE_JOBS = 'qa_active_transcription_jobs'

export function useTranscription() {
  const { toast } = useToast()
  const { addOrUpdateJob, removeJob, cancelJob } = useBackgroundJobs()

  // View mode
  const [viewMode, setViewMode] = useState<'dashboard' | 'studio'>('dashboard')

  // Data lists
  const [activeJobs, setActiveJobs] = useState<Record<string, TranscriptionProgress>>({})
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

  // Fetch available models and restore persisted jobs on mount
  useEffect(() => {
    transcriptionApi
      .getAvailableModels()
      .then(setAvailableModels)
      .catch((e) => console.warn('Could not load models info:', e))

    refreshTranscriptions()

    // Restore jobs from localStorage (filtering out stale upload_ jobs)
    try {
      const stored = localStorage.getItem(LOCAL_STORAGE_ACTIVE_JOBS)
      if (stored) {
        const parsed: Record<string, TranscriptionProgress> = JSON.parse(stored)
        const validJobs: Record<string, TranscriptionProgress> = {}
        for (const [id, job] of Object.entries(parsed)) {
          if (!id.startsWith('upload_')) {
            validJobs[id] = job
          }
        }
        if (Object.keys(validJobs).length > 0) {
          setActiveJobs(validJobs)
        }
      }
    } catch (e) {
      console.warn('Error reading active jobs from storage:', e)
    }
  }, [refreshTranscriptions])

  // Save active jobs changes to localStorage
  useEffect(() => {
    saveActiveJobsToStorage(activeJobs)
  }, [activeJobs, saveActiveJobsToStorage])

  // SSE connections for active jobs
  const eventSourcesRef = useRef<Record<string, EventSource>>({})

  // Manage SSE connections and polling fallback for active jobs
  useEffect(() => {
    const activeIds = Object.keys(activeJobs).filter(
      (id) =>
        !id.startsWith('upload_') &&
        activeJobs[id].status !== 'complete' &&
        activeJobs[id].status !== 'failed' &&
        activeJobs[id].status !== 'cancelled' &&
        activeJobs[id].status !== 'uploading'
    )

    // Open EventSource for each active job
    for (const id of activeIds) {
      if (!eventSourcesRef.current[id]) {
        try {
          const streamUrl = transcriptionApi.getProgressStreamUrl(id)
          const es = new EventSource(streamUrl)
          eventSourcesRef.current[id] = es

          es.addEventListener('message', async (event) => {
            try {
              const data = JSON.parse(event.data)
              if (data.stage === 'heartbeat' || data.event === 'heartbeat' || data.event === 'connected') {
                return
              }

              setActiveJobs((prev) => {
                const existing = prev[id]
                return {
                  ...prev,
                  [id]: {
                    id,
                    media_id: existing?.media_id || data.media_id || '',
                    title: data.title || existing?.title,
                    status: data.stage === 'complete' ? 'complete' : data.stage === 'failed' ? 'failed' : 'transcribing',
                    stage: data.stage || existing?.stage,
                    progress: typeof data.progress === 'number' ? data.progress : existing?.progress || 0,
                    message: data.message || existing?.message || 'Procesando audio...',
                    preview: data.preview,
                    eta: data.eta || existing?.eta,
                    model_info: data.model_info || existing?.model_info,
                    error: data.error,
                  },
                }
              })

              if (data.stage === 'complete' || data.progress === 100) {
                await refreshTranscriptions()
                es.close()
                delete eventSourcesRef.current[id]
              } else if (data.stage === 'failed') {
                es.close()
                delete eventSourcesRef.current[id]
              }
            } catch (err) {
              console.warn('Error parsing SSE in useTranscription:', err)
            }
          })

          es.addEventListener('error', () => {
            // Keep fallback polling alive
          })
        } catch (e) {
          console.warn('Could not start EventSource for job:', id, e)
        }
      }
    }

    // Clean up closed EventSources for finished/dismissed jobs
    for (const id of Object.keys(eventSourcesRef.current)) {
      if (!activeIds.includes(id)) {
        eventSourcesRef.current[id]?.close()
        delete eventSourcesRef.current[id]
      }
    }

    // Fallback polling loop (every 3 seconds) for resilience
    if (activeIds.length > 0 && !pollingTimerRef.current) {
      pollingTimerRef.current = window.setInterval(async () => {
        for (const id of activeIds) {
          try {
            const status = await transcriptionApi.getTranscriptionStatus(id)
            setActiveJobs((prev) => ({
              ...prev,
              [id]: status,
            }))

            if (status.status === 'complete' || status.progress === 100) {
              await refreshTranscriptions()
            }
          } catch {
            // Fallback check
          }
        }
      }, 3000)
    } else if (activeIds.length === 0 && pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current)
      pollingTimerRef.current = null
    }

    return () => {
      // Retain connections during rerenders
    }
  }, [activeJobs, refreshTranscriptions])

  // Clean up all EventSources on unmount
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current)
        pollingTimerRef.current = null
      }
      for (const es of Object.values(eventSourcesRef.current)) {
        es?.close()
      }
      eventSourcesRef.current = {}
    }
  }, [])

  // Start upload and transcription pipeline -> auto-transition to Studio
  const handleUploadAndStart = async (file: File, title: string, description: string = '') => {
    // Generate the definitive transcription ID upfront so the same ID is used for the entire lifecycle
    const transcriptionId =
      typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `trans_${Date.now()}`

    try {
      setIsUploading(true)
      setActiveMeetingTitle(title)

      const initialUploadJob = {
        id: transcriptionId,
        media_id: '',
        title,
        status: 'uploading' as const,
        stage: 'uploading',
        progress: 5,
        message: `Iniciando subida de "${file.name}"...`,
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
        progress: 5,
        status: 'uploading',
        stageText: `Iniciando subida de "${file.name}"...`,
        onCancel: () => void handleCancelTranscription(transcriptionId),
        onDismiss: () => handleDismissJob(transcriptionId),
      })

      // 1. Upload media with real-time XMLHttpRequest progress
      const uploadRes = await transcriptionApi.uploadMediaWithProgress(
        file,
        title,
        description,
        (prog, msg) => {
          const calculatedProgress = Math.min(10, Math.max(5, Math.round(prog / 10)))
          setActiveJobs((prev) => {
            if (!prev[transcriptionId]) return prev
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
          })
        },
        transcriptionId
      )

      const mediaId = uploadRes.media_id

      // Transition to preprocessing with the exact same ID
      const preprocessingJob = {
        id: transcriptionId,
        media_id: mediaId,
        title,
        status: 'preprocessing' as const,
        stage: 'preprocessing',
        progress: 15,
        message: 'Archivo cargado. Extrayendo audio...',
        eta: '~45 s',
        model_info: availableModels?.active_model_label || 'Whisper Auto',
      }
      setActiveJobs((prev) => ({
        ...prev,
        [transcriptionId]: preprocessingJob,
      }))
      addOrUpdateJob({
        id: transcriptionId,
        type: 'transcription',
        title,
        progress: 15,
        status: 'preprocessing',
        stageText: 'Archivo cargado. Extrayendo audio...',
        eta: '~45 s',
      })

      setSelectedTranscriptionId(transcriptionId)

      // 2. Start transcription on backend
      await transcriptionApi.startTranscription(mediaId, {
        transcription_id: transcriptionId,
        mode: 'auto',
        enable_diarization: true,
      })

      // Transition immediately to the Live Transcription Studio
      setViewMode('studio')
    } catch (err: any) {
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

  // Cancel transcription
  const handleCancelTranscription = async (transcriptionId: string) => {
    try {
      await cancelJob(transcriptionId)
      setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })
      if (selectedTranscriptionId === transcriptionId && viewMode === 'studio') {
        setViewMode('dashboard')
      }
      setShowProgressModal(false)
      await refreshTranscriptions()
    } catch (err: any) {
      console.warn('Error cancelling transcription:', err)
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

  // Navigation helpers
  const openStudio = (transcriptionId: string) => {
    setSelectedTranscriptionId(transcriptionId)
    const active = activeJobs[transcriptionId]
    const recent = recentTranscriptions.find((t) => t.id === transcriptionId)
    if (active?.title) {
      setActiveMeetingTitle(active.title)
    } else if (recent?.metadata?.title) {
      setActiveMeetingTitle(recent.metadata.title)
    }
    setViewMode('studio')
  }

  const closeStudio = () => {
    setViewMode('dashboard')
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

  const handleDismissJob = (id: string) => {
    setActiveJobs((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    removeJob(id)
  }

  // Active progress for selected transcription
  const currentProgress = selectedTranscriptionId ? activeJobs[selectedTranscriptionId] || null : null

  return {
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
}
