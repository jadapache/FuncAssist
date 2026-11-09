import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
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
import { useAuth } from '../../../context/AuthContext'
import { useTranscriptionModals } from '../hooks/useTranscriptionModals'
import { useTranscriptionStreamManager } from '../hooks/useTranscriptionStreamManager'
import { useTranscriptionPipeline } from '../hooks/useTranscriptionPipeline'
import {
  STAGE_TRANSLATIONS,
  getGeneralStageText,
  getTranscriptionStageText,
} from '../utils/transcriptionStages'
import {
  loadStoredActiveJobs,
  saveActiveJobsToStorage,
} from '../utils/transcriptionStorage'

export { STAGE_TRANSLATIONS, getGeneralStageText, getTranscriptionStageText }

export interface TranscriptionContextValue {
  viewMode: 'dashboard' | 'studio'
  setViewMode: React.Dispatch<React.SetStateAction<'dashboard' | 'studio'>>
  openStudio: (transcriptionId: string, title?: string) => void
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
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth()

  const modals = useTranscriptionModals()
  const [activeJobs, setActiveJobs] = useState<Record<string, TranscriptionProgress>>({})
  const [recentTranscriptions, setRecentTranscriptions] = useState<TranscriptionResult[]>([])
  const [availableModels, setAvailableModels] = useState<AvailableModelsInfo | null>(null)
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [isUploading, setIsUploading] = useState(false)

  const refreshTranscriptions = useCallback(async () => {
    if (!isAuthenticated) return
    try {
      setIsLoadingList(true)
      const res = await transcriptionApi.listTranscriptions()
      setRecentTranscriptions(res.transcriptions || [])
    } catch (err) {
      console.warn('Error fetching transcriptions list:', err)
    } finally {
      setIsLoadingList(false)
    }
  }, [isAuthenticated])

  const streamManager = useTranscriptionStreamManager({
    isAuthenticated,
    isAuthLoading,
    activeJobs,
    setActiveJobs,
    addOrUpdateJob,
    removeJob,
    cancelJob,
    openStudio: modals.openStudio,
    refreshTranscriptions,
  })

  const pipeline = useTranscriptionPipeline({
    availableModels,
    activeJobs,
    setActiveJobs,
    recentTranscriptions,
    setRecentTranscriptions,
    setIsUploading,
    openStudio: modals.openStudio,
    setActiveMeetingTitle: modals.setActiveMeetingTitle,
    setSelectedTranscriptionId: modals.setSelectedTranscriptionId,
    selectedTranscriptionId: modals.selectedTranscriptionId,
    activeMeetingTitle: modals.activeMeetingTitle,
    setViewMode: modals.setViewMode,
    addOrUpdateJob,
    removeJob,
    handleCancelTranscription: streamManager.handleCancelTranscription,
    handleDismissJob: streamManager.handleDismissJob,
    toast,
    abortControllersRef: streamManager.abortControllersRef,
    cancelledJobsRef: streamManager.cancelledJobsRef,
    activeWorkersRef: streamManager.activeWorkersRef,
    clientJobIdsRef: streamManager.clientJobIdsRef,
  })

  // Stabilize callbacks for persisted jobs to avoid re-triggering initialization effects
  const openStudioRef = React.useRef(modals.openStudio)
  openStudioRef.current = modals.openStudio

  const cancelTranscriptionRef = React.useRef(streamManager.handleCancelTranscription)
  cancelTranscriptionRef.current = streamManager.handleCancelTranscription

  const dismissJobRef = React.useRef(streamManager.handleDismissJob)
  dismissJobRef.current = streamManager.handleDismissJob

  // Restore stored active jobs on authentication
  const restorePersistedJobs = useCallback(() => {
    const validJobs = loadStoredActiveJobs()
    if (Object.keys(validJobs).length === 0) return

    setActiveJobs(validJobs)
    for (const [id, job] of Object.entries(validJobs)) {
      addOrUpdateJob({
        id,
        type: 'transcription',
        title: job.title || 'Transcripción',
        progress: typeof job.progress === 'number' ? job.progress : 0,
        status: job.status,
        stageText: getTranscriptionStageText(job),
        speedOrSize: job.preview || null,
        eta: job.eta || null,
        onClick: () => {
          openStudioRef.current(id)
          navigate('/funcional/transcripciones')
        },
        onCancel: () => void cancelTranscriptionRef.current(id),
        onDismiss: () => dismissJobRef.current(id),
      })
    }
  }, [addOrUpdateJob, navigate])

  // Fetch available models and restore persisted jobs on mount / auth change
  useEffect(() => {
    if (!isAuthenticated || isAuthLoading) {
      setRecentTranscriptions([])
      setAvailableModels(null)
      return
    }

    transcriptionApi
      .getAvailableModels()
      .then(setAvailableModels)
      .catch((e) => console.warn('Could not load models info:', e))

    void refreshTranscriptions()
    restorePersistedJobs()
  }, [isAuthenticated, isAuthLoading, refreshTranscriptions, restorePersistedJobs])

  // Save active jobs changes to localStorage
  useEffect(() => {
    saveActiveJobsToStorage(activeJobs, streamManager.clientJobIdsRef.current)
  }, [activeJobs, streamManager.clientJobIdsRef])

  const currentProgress = modals.selectedTranscriptionId
    ? activeJobs[modals.selectedTranscriptionId] || null
    : null

  const value: TranscriptionContextValue = {
    viewMode: modals.viewMode,
    setViewMode: modals.setViewMode,
    openStudio: modals.openStudio,
    closeStudio: modals.closeStudio,
    activeJobs: Object.values(activeJobs),
    recentTranscriptions,
    availableModels,
    isLoadingList,
    isUploading,
    showProgressModal: modals.showProgressModal,
    showSummaryModal: modals.showSummaryModal,
    showGenerateModal: modals.showGenerateModal,
    selectedTranscriptionId: modals.selectedTranscriptionId,
    activeMeetingTitle: modals.activeMeetingTitle,
    currentProgress,
    handleUploadAndStart: pipeline.handleUploadAndStart,
    handleRetranscribe: pipeline.handleRetranscribe,
    handleCancelTranscription: streamManager.handleCancelTranscription,
    handleDeleteTranscription: pipeline.handleDeleteTranscription,
    handleDismissJob: streamManager.handleDismissJob,
    openProgressModal: modals.openProgressModal,
    openSummaryModal: modals.openSummaryModal,
    openGenerateModal: modals.openGenerateModal,
    closeAllModals: modals.closeAllModals,
    setShowProgressModal: modals.setShowProgressModal,
    setShowSummaryModal: modals.setShowSummaryModal,
    setShowGenerateModal: modals.setShowGenerateModal,
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
