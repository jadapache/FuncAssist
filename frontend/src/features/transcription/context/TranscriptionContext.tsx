import React, { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'
import { useAuth } from '../../../context/AuthContext'
import { useTranscriptionModals } from '../hooks/useTranscriptionModals'
import { useServerJobStreams } from '../hooks/useServerJobStreams'
import {
  isCloudTranscriptionProvider,
  useTranscriptionJobRunners,
  type UploadJobOptions,
} from '../hooks/useTranscriptionJobRunners'
import { useBeforeUnloadGuard, useJobNotifications, useJobPersistence } from '../hooks/useJobLifecycle'
import { useBackgroundJobsAdapter } from '../hooks/useBackgroundJobsAdapter'
import { useLatest } from '../hooks/useLatest'
import { generateTranscriptionSlug } from '../utils/transcriptionStorage'
import { isTerminalStage } from '../utils/transcriptionStages'
import { jobsReducer, type TranscriptionJob } from './transcriptionJobs'
import { TranscriptionContext, type TranscriptionContextValue } from './transcriptionContextValue'

export const TranscriptionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { toast } = useToast()
  const navigate = useNavigate()
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth()
  const enabled = isAuthenticated && !isAuthLoading

  const modals = useTranscriptionModals()
  const { openStudio, closeStudio, selectedTranscriptionId, setSelectedTranscriptionId } = modals

  const [jobsState, dispatch] = useReducer(jobsReducer, {})
  const jobsRef = useLatest(jobsState)
  const jobs = useMemo(() => Object.values(jobsState).sort((a, b) => b.startedAt - a.startedAt), [jobsState])

  const [recentTranscriptions, setRecentTranscriptions] = useState<TranscriptionResult[]>([])
  const [availableModels, setAvailableModels] = useState<AvailableModelsInfo | null>(null)
  const [isLoadingList, setIsLoadingList] = useState(false)

  const refreshTranscriptions = useCallback(async () => {
    if (!enabled) return
    try {
      setIsLoadingList(true)
      const res = await transcriptionApi.listTranscriptions()
      setRecentTranscriptions(res.transcriptions || [])
    } catch (err) {
      console.warn('Error fetching transcriptions list:', err)
    } finally {
      setIsLoadingList(false)
    }
  }, [enabled])

  const upsertRecent = useCallback((record: TranscriptionResult) => {
    setRecentTranscriptions((prev) => {
      const index = prev.findIndex((item) => item.id === record.id)
      if (index < 0) return [record, ...prev]
      const next = [...prev]
      next[index] = record
      return next
    })
  }, [])

  const showJob = useCallback(
    (id: string, title: string) => {
      openStudio(id, title)
      navigate(`/transcripciones/${generateTranscriptionSlug(title, id)}`)
    },
    [openStudio, navigate],
  )

  const runners = useTranscriptionJobRunners({
    dispatch,
    jobsRef,
    availableModels,
    toast,
    onRecordSaved: upsertRecent,
    onJobCreated: showJob,
  })
  const { startServerJob, startBrowserJob, cancel, retry, regenerate } = runners

  useServerJobStreams({
    jobs,
    dispatch,
    enabled,
    onNotFound: (id) =>
      dispatch({
        type: 'update',
        id,
        patch: { stage: 'failed', error: 'El trabajo de transcripción ya no existe en el servidor.', retryable: false },
      }),
    onFatal: (id, message) => dispatch({ type: 'update', id, patch: { stage: 'failed', error: message, retryable: false } }),
  })
  useJobPersistence({ jobs, dispatch, enabled, toast })
  useJobNotifications({
    jobs,
    jobsRef,
    dispatch,
    toast,
    onCompleted: () => void refreshTranscriptions(),
  })
  useBeforeUnloadGuard(jobs)

  const dismissJob = useCallback(
    (id: string) => {
      const job = jobsRef.current[id]
      if (!job) return
      dispatch(isTerminalStage(job.stage) ? { type: 'remove', id } : { type: 'hide_toast', id })
    },
    [jobsRef],
  )

  useBackgroundJobsAdapter(jobs, {
    open: (job: TranscriptionJob) => showJob(job.id, job.title),
    cancel: (id) => void cancel(id),
    dismiss: dismissJob,
  })

  // Models info and list on login
  useEffect(() => {
    if (!enabled) {
      setRecentTranscriptions([])
      setAvailableModels(null)
      return
    }
    transcriptionApi
      .getAvailableModels()
      .then(setAvailableModels)
      .catch((e) => console.warn('Could not load models info:', e))
    void refreshTranscriptions()
  }, [enabled, refreshTranscriptions])

  const startTranscription = useCallback(
    async (file: File, title: string, description: string, options: UploadJobOptions) => {
      // Decide the path with fresh info if it was not loaded yet.
      const models = availableModels ?? (await transcriptionApi.getAvailableModels().catch(() => null))
      if (models && !availableModels) setAvailableModels(models)
      if (isCloudTranscriptionProvider(models)) await startServerJob(file, title, description, options)
      else await startBrowserJob(file, title, description, options)
    },
    [availableModels, startServerJob, startBrowserJob],
  )

  const deleteTranscription = useCallback(
    async (transcriptionId: string) => {
      try {
        const job = jobsRef.current[transcriptionId]
        if (job && !isTerminalStage(job.stage)) await cancel(transcriptionId)
        await transcriptionApi.deleteTranscription(transcriptionId)
        setRecentTranscriptions((prev) => prev.filter((t) => t.id !== transcriptionId))
        dispatch({ type: 'remove', id: transcriptionId })
        if (selectedTranscriptionId === transcriptionId) {
          closeStudio()
          setSelectedTranscriptionId(null)
        }
        toast.success('Transcripción eliminada con éxito.')
      } catch (err) {
        toast.error(`Error al eliminar: ${err instanceof Error ? err.message : 'error desconocido'}`)
      }
    },
    [cancel, closeStudio, jobsRef, selectedTranscriptionId, setSelectedTranscriptionId, toast],
  )

  const currentJob = selectedTranscriptionId ? jobsState[selectedTranscriptionId] ?? null : null
  const isCloudProvider = isCloudTranscriptionProvider(availableModels)

  const value = useMemo<TranscriptionContextValue>(
    () => ({
      viewMode: modals.viewMode,
      openStudio,
      closeStudio,
      activeJobs: jobs,
      currentJob,
      recentTranscriptions,
      availableModels,
      isCloudProvider,
      isLoadingList,
      showGenerateModal: modals.showGenerateModal,
      setShowGenerateModal: modals.setShowGenerateModal,
      selectedTranscriptionId,
      activeMeetingTitle: modals.activeMeetingTitle,
      startTranscription,
      regenerateTranscription: regenerate,
      retryTranscription: retry,
      cancelTranscription: cancel,
      dismissJob,
      deleteTranscription,
      refreshTranscriptions,
      upsertRecent,
    }),
    [
      modals.viewMode,
      modals.showGenerateModal,
      modals.setShowGenerateModal,
      modals.activeMeetingTitle,
      openStudio,
      closeStudio,
      jobs,
      currentJob,
      recentTranscriptions,
      availableModels,
      isCloudProvider,
      isLoadingList,
      selectedTranscriptionId,
      startTranscription,
      regenerate,
      retry,
      cancel,
      dismissJob,
      deleteTranscription,
      refreshTranscriptions,
      upsertRecent,
    ],
  )

  return <TranscriptionContext.Provider value={value}>{children}</TranscriptionContext.Provider>
}
