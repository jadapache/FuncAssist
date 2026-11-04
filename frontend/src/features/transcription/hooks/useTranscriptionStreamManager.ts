import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  transcriptionApi,
  type TranscriptionProgress,
} from '../api/transcriptionApi'
import {
  getGeneralStageText,
  getTranscriptionStageText,
} from '../utils/transcriptionStages'

interface StreamManagerProps {
  isAuthenticated: boolean
  isAuthLoading: boolean
  activeJobs: Record<string, TranscriptionProgress>
  setActiveJobs: React.Dispatch<React.SetStateAction<Record<string, TranscriptionProgress>>>
  addOrUpdateJob: (job: any) => void
  removeJob: (id: string) => void
  cancelJob: (id: string) => Promise<void>
  openStudio: (id: string) => void
  refreshTranscriptions: () => Promise<void>
}

export function useTranscriptionStreamManager({
  isAuthenticated,
  isAuthLoading,
  activeJobs,
  setActiveJobs,
  addOrUpdateJob,
  removeJob,
  cancelJob,
  openStudio,
  refreshTranscriptions,
}: StreamManagerProps) {
  const navigate = useNavigate()
  const activeJobsRef = useRef(activeJobs)
  useEffect(() => {
    activeJobsRef.current = activeJobs
  }, [activeJobs])

  const pollingTimerRef = useRef<number | null>(null)
  const eventSourcesRef = useRef<Record<string, EventSource>>({})
  const abortControllersRef = useRef<Record<string, AbortController>>({})
  const cancelledJobsRef = useRef<Set<string>>(new Set())
  const activeWorkersRef = useRef<Record<string, Worker>>({})
  const clientJobIdsRef = useRef<Set<string>>(new Set())

  const handleDismissJob = useCallback((id: string) => {
    clientJobIdsRef.current.delete(id)
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
  }, [removeJob, setActiveJobs])

  const handleCancelTranscription = useCallback(
    async (transcriptionId: string) => {
      try {
        cancelledJobsRef.current.add(transcriptionId)

        if (abortControllersRef.current[transcriptionId]) {
          abortControllersRef.current[transcriptionId].abort()
          delete abortControllersRef.current[transcriptionId]
        }
        if (eventSourcesRef.current[transcriptionId]) {
          eventSourcesRef.current[transcriptionId].close()
          delete eventSourcesRef.current[transcriptionId]
        }
        if (activeWorkersRef.current[transcriptionId]) {
          activeWorkersRef.current[transcriptionId].terminate()
          delete activeWorkersRef.current[transcriptionId]
        }

        setActiveJobs((prev) => {
          const next = { ...prev }
          delete next[transcriptionId]
          return next
        })

        await cancelJob(transcriptionId)
        await refreshTranscriptions()
      } catch (err) {
        console.warn('Error cancelling transcription:', err)
      }
    },
    [cancelJob, refreshTranscriptions, setActiveJobs],
  )

  const activeIdsKey = useMemo(() => {
    return Object.keys(activeJobs)
      .filter((id) => {
        const job = activeJobs[id]
        if (id.startsWith('upload_') || clientJobIdsRef.current.has(id)) return false
        if (job?.model_info === 'Whisper Web (Client)') return false
        const inactive = ['complete', 'failed', 'cancelled', 'uploading']
        return !inactive.includes(job?.status)
      })
      .sort()
      .join(',')
  }, [activeJobs])

  const syncJobUi = useCallback(
    (id: string, title: string, progress: number, status: string, stageText: string, eta?: string | null) => {
      addOrUpdateJob({
        id,
        type: 'transcription',
        title,
        progress,
        status,
        stageText,
        speedOrSize: null,
        eta: eta || null,
        onClick: () => {
          openStudio(id)
          navigate('/funcional/transcripciones')
        },
        onCancel: () => void handleCancelTranscription(id),
        onDismiss: () => handleDismissJob(id),
      })
    },
    [addOrUpdateJob, handleCancelTranscription, handleDismissJob, navigate, openStudio],
  )

  const processJobPayload = useCallback(
    async (id: string, data: any) => {
      if (cancelledJobsRef.current.has(id)) return

      const isCancelled = data.stage === 'cancelled' || data.status === 'cancelled'
      if (isCancelled) {
        cancelledJobsRef.current.add(id)
        eventSourcesRef.current[id]?.close()
        delete eventSourcesRef.current[id]
        setActiveJobs((prev) => {
          const next = { ...prev }
          delete next[id]
          return next
        })
        syncJobUi(id, data.title || 'Transcripción', 0, 'cancelled', 'Transcripción cancelada')
        return
      }

      const updatedProgress = typeof data.progress === 'number' ? data.progress : 0
      const isDone = data.stage === 'complete' || updatedProgress === 100
      const isFail = data.stage === 'failed'
      const updatedStatus: TranscriptionProgress['status'] = isDone ? 'complete' : isFail ? 'failed' : 'transcribing'
      const stageText = getTranscriptionStageText(data)
      const generalStageText = getGeneralStageText(data)

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
            message: data.message || stageText,
            preview: data.preview,
            eta: isDone || isFail ? null : data.eta || existing?.eta,
            model_info: data.model_info || existing?.model_info,
            error: data.error,
            live_segments: data.live_segments || existing?.live_segments || [],
            live_text: data.live_text || existing?.live_text || '',
          },
        }
      })

      syncJobUi(
        id,
        data.title || activeJobsRef.current[id]?.title || 'Transcripción',
        isDone ? 100 : updatedProgress,
        updatedStatus,
        generalStageText,
        isDone || isFail ? null : data.eta,
      )

      if (isDone || isFail) {
        eventSourcesRef.current[id]?.close()
        delete eventSourcesRef.current[id]
        if (isDone) await refreshTranscriptions()
      }
    },
    [refreshTranscriptions, setActiveJobs, syncJobUi],
  )

  useEffect(() => {
    if (!isAuthenticated || isAuthLoading) return
    const activeIds = activeIdsKey ? activeIdsKey.split(',') : []

    for (const id of activeIds) {
      if (clientJobIdsRef.current.has(id) || eventSourcesRef.current[id]) continue
      try {
        const es = new EventSource(transcriptionApi.getProgressStreamUrl(id))
        eventSourcesRef.current[id] = es

        es.addEventListener('message', (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.stage === 'heartbeat' || data.event === 'heartbeat' || data.event === 'connected') return
            void processJobPayload(id, data)
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
      } catch (err) {
        console.warn('Could not start EventSource for job:', id, err)
      }
    }

    for (const id of Object.keys(eventSourcesRef.current)) {
      if (!activeIds.includes(id)) {
        eventSourcesRef.current[id]?.close()
        delete eventSourcesRef.current[id]
      }
    }

    if (activeIds.length > 0 && !pollingTimerRef.current) {
      pollingTimerRef.current = window.setInterval(async () => {
        const currentActive = Object.keys(activeJobsRef.current).filter((id) => {
          const job = activeJobsRef.current[id]
          if (id.startsWith('upload_') || clientJobIdsRef.current.has(id)) return false
          if (job?.model_info === 'Whisper Web (Client)') return false
          const inactive = ['complete', 'failed', 'cancelled', 'uploading']
          return !inactive.includes(job?.status)
        })

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
            if (!status) continue
            await processJobPayload(id, status)
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err)
            if (msg.includes('404')) {
              setActiveJobs((prev) => {
                const next = { ...prev }
                delete next[id]
                return next
              })
              removeJob(id)
            }
          }
        }
      }, 2500)
    } else if (activeIds.length === 0 && pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current)
      pollingTimerRef.current = null
    }
  }, [activeIdsKey, isAuthenticated, isAuthLoading, processJobPayload, removeJob, setActiveJobs])

  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current)
        pollingTimerRef.current = null
      }
      for (const ctrl of Object.values(abortControllersRef.current)) {
        ctrl.abort()
      }
      abortControllersRef.current = {}
      for (const es of Object.values(eventSourcesRef.current)) {
        es?.close()
      }
      eventSourcesRef.current = {}
    }
  }, [])

  return {
    handleCancelTranscription,
    handleDismissJob,
    abortControllersRef,
    cancelledJobsRef,
    activeWorkersRef,
    clientJobIdsRef,
  }
}

