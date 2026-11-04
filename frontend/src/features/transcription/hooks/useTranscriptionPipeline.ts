import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionProgress,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { runClientTranscription, resolveClientOnnxModel } from '../utils/clientTranscription'

interface PipelineProps {
  availableModels: AvailableModelsInfo | null
  activeJobs: Record<string, TranscriptionProgress>
  setActiveJobs: React.Dispatch<React.SetStateAction<Record<string, TranscriptionProgress>>>
  recentTranscriptions: TranscriptionResult[]
  setRecentTranscriptions: React.Dispatch<React.SetStateAction<TranscriptionResult[]>>
  setIsUploading: (val: boolean) => void
  openStudio: (id: string, title?: string) => void
  setActiveMeetingTitle: (title: string) => void
  setSelectedTranscriptionId: (id: string | null) => void
  selectedTranscriptionId: string | null
  activeMeetingTitle: string
  setViewMode: React.Dispatch<React.SetStateAction<'dashboard' | 'studio'>>
  addOrUpdateJob: (job: any) => void
  removeJob: (id: string) => void
  handleCancelTranscription: (id: string) => Promise<void>
  handleDismissJob: (id: string) => void
  toast: any
  abortControllersRef: React.MutableRefObject<Record<string, AbortController>>
  cancelledJobsRef: React.MutableRefObject<Set<string>>
  activeWorkersRef: React.MutableRefObject<Record<string, Worker>>
  clientJobIdsRef: React.MutableRefObject<Set<string>>
}

export function useTranscriptionPipeline(props: PipelineProps) {
  const navigate = useNavigate()
  const {
    availableModels,
    activeJobs,
    setActiveJobs,
    recentTranscriptions,
    setRecentTranscriptions,
    setIsUploading,
    openStudio,
    setActiveMeetingTitle,
    setSelectedTranscriptionId,
    selectedTranscriptionId,
    activeMeetingTitle,
    setViewMode,
    addOrUpdateJob,
    removeJob,
    handleCancelTranscription,
    handleDismissJob,
    toast,
    abortControllersRef,
    cancelledJobsRef,
    activeWorkersRef,
    clientJobIdsRef,
  } = props

  const executeClientAudioPath = async (
    transcriptionId: string,
    file: File,
    title: string,
    description: string,
  ) => {
    clientJobIdsRef.current.add(transcriptionId)
    setSelectedTranscriptionId(transcriptionId)

    const clientInitJob: TranscriptionProgress = {
      id: transcriptionId,
      media_id: transcriptionId,
      title,
      status: 'preprocessing',
      stage: 'preprocessing',
      progress: 0,
      message: 'Iniciando proceso...',
      eta: null,
      model_info: 'Whisper Web (Client)',
    }
    setActiveJobs((prev) => ({ ...prev, [transcriptionId]: clientInitJob }))
    addOrUpdateJob({
      id: transcriptionId,
      type: 'transcription',
      title,
      progress: 0,
      status: 'preprocessing',
      stageText: 'Iniciando proceso...',
      eta: null,
      onClick: () => {
        openStudio(transcriptionId)
        navigate('/funcional/transcripciones')
      },
      onCancel: () => void handleCancelTranscription(transcriptionId),
      onDismiss: () => handleDismissJob(transcriptionId),
    })

    const modelId = resolveClientOnnxModel(availableModels?.configured_model)
    const result = await runClientTranscription({
      id: transcriptionId,
      file,
      title,
      description,
      language: 'es',
      modelId,
      onProgress: (prog) => {
        setActiveJobs((prev) => {
          if (!prev[transcriptionId]) return prev
          return {
            ...prev,
            [transcriptionId]: {
              ...prev[transcriptionId],
              progress: prog.progress,
              stage: prog.stage,
              status: prog.stage,
              message: prog.message,
              eta: prog.eta !== undefined ? prog.eta : prev[transcriptionId]?.eta,
              live_text: prog.live_text,
              live_segments: prog.live_segments,
              model_info: prog.model_info || prev[transcriptionId]?.model_info,
            },
          }
        })
        addOrUpdateJob({
          id: transcriptionId,
          type: 'transcription',
          title,
          progress: prog.progress,
          status: prog.stage,
          stageText: prog.message,
          speedOrSize: prog.live_text ? `${prog.live_text.slice(0, 60)}...` : null,
          eta: prog.eta || null,
          onClick: () => {
            openStudio(transcriptionId)
            navigate('/funcional/transcripciones')
          },
          onCancel: () => void handleCancelTranscription(transcriptionId),
          onDismiss: () => handleDismissJob(transcriptionId),
        })
      },
      onRegisterWorker: (worker) => {
        activeWorkersRef.current[transcriptionId] = worker
      },
      isCancelled: () => cancelledJobsRef.current.has(transcriptionId),
    })

    delete activeWorkersRef.current[transcriptionId]
    clientJobIdsRef.current.delete(transcriptionId)
    if (cancelledJobsRef.current.has(transcriptionId)) return

    setRecentTranscriptions((prev) => [
      result.transcription,
      ...prev.filter((t) => t.id !== transcriptionId),
    ])
    setActiveJobs((prev) => {
      const next = { ...prev }
      delete next[transcriptionId]
      return next
    })
    addOrUpdateJob({
      id: transcriptionId,
      type: 'transcription',
      title,
      progress: 100,
      status: 'complete',
      stageText: 'Completado con éxito',
      onClick: () => {
        openStudio(transcriptionId)
        navigate('/funcional/transcripciones')
      },
      onDismiss: () => handleDismissJob(transcriptionId),
    })
    toast.success('Transcripción completada con éxito.')
    setViewMode('studio')
  }

  const executeServerAudioPath = async (
    transcriptionId: string,
    localPath: string,
    title: string,
    description: string,
  ) => {
    const regRes = await transcriptionApi.registerLocalPath(
      localPath.trim(),
      title,
      description,
      transcriptionId,
    )
    const mediaId = regRes.media_id || transcriptionId

    delete abortControllersRef.current[transcriptionId]
    if (cancelledJobsRef.current.has(transcriptionId)) return

    const preprocessingJob: TranscriptionProgress = {
      id: transcriptionId,
      media_id: mediaId,
      title,
      status: 'preprocessing',
      stage: 'preprocessing',
      progress: 0,
      message: 'Iniciando transcripción...',
      eta: null,
      model_info: availableModels?.active_model_label || 'Whisper Auto',
    }
    setActiveJobs((prev) => {
      if (cancelledJobsRef.current.has(transcriptionId)) return prev
      return { ...prev, [transcriptionId]: preprocessingJob }
    })
    addOrUpdateJob({
      id: transcriptionId,
      type: 'transcription',
      title,
      progress: 0,
      status: 'preprocessing',
      stageText: 'Iniciando transcripción...',
      eta: null,
      onClick: () => {
        openStudio(transcriptionId)
        navigate('/funcional/transcripciones')
      },
      onCancel: () => void handleCancelTranscription(transcriptionId),
      onDismiss: () => handleDismissJob(transcriptionId),
    })

    setSelectedTranscriptionId(transcriptionId)
    if (cancelledJobsRef.current.has(transcriptionId)) return

    await transcriptionApi.startTranscription(mediaId, {
      transcription_id: transcriptionId,
      mode: 'auto',
      enable_diarization: true,
    })

    if (!cancelledJobsRef.current.has(transcriptionId)) {
      setViewMode('studio')
    }
  }

  const handleUploadAndStart = useCallback(
    async (target: any, title: string, description: string = '') => {
      const transcriptionId =
        typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `trans_${Date.now()}`

      cancelledJobsRef.current.delete(transcriptionId)
      abortControllersRef.current[transcriptionId] = new AbortController()
      const localPath = ((target as any)?.path || (target as any)?.filePath || '') as string

      try {
        setIsUploading(true)
        setActiveMeetingTitle(title)

        if (!localPath && target instanceof File) {
          await executeClientAudioPath(transcriptionId, target, title, description)
          return
        }

        if (!localPath || typeof localPath !== 'string' || localPath.trim().length === 0) {
          throw new Error('No se pudo resolver la ruta local del archivo multimedia.')
        }

        await executeServerAudioPath(transcriptionId, localPath, title, description)
      } catch (err: unknown) {
        delete abortControllersRef.current[transcriptionId]
        clientJobIdsRef.current.delete(transcriptionId)
        if (cancelledJobsRef.current.has(transcriptionId)) return

        setActiveJobs((prev) => {
          const next = { ...prev }
          delete next[transcriptionId]
          return next
        })
        removeJob(transcriptionId)
        toast.error(err instanceof Error ? err.message : 'Error durante la transcripción.')
      } finally {
        setIsUploading(false)
      }
    },
    [availableModels, toast, setViewMode, setIsUploading, setActiveMeetingTitle],
  )

  const handleDeleteTranscription = useCallback(
    async (transcriptionId: string) => {
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
    },
    [removeJob, selectedTranscriptionId, setActiveJobs, setRecentTranscriptions, setSelectedTranscriptionId, setViewMode, toast],
  )

  const handleRetranscribe = useCallback(
    async (transcriptionId: string, title?: string) => {
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
          progress: 0,
          message: 'Iniciando regeneración con el motor configurado...',
          eta: null,
          model_info: availableModels?.active_model_label || 'Whisper Auto',
        }
        setActiveJobs((prev) => ({ ...prev, [transcriptionId]: retransJob }))
        addOrUpdateJob({
          id: transcriptionId,
          type: 'transcription',
          title: jobTitle,
          progress: 0,
          status: 'preprocessing',
          stageText: 'Iniciando regeneración con el motor configurado...',
          eta: null,
          onClick: () => {
            openStudio(transcriptionId)
            navigate('/funcional/transcripciones')
          },
          onCancel: () => void handleCancelTranscription(transcriptionId),
          onDismiss: () => handleDismissJob(transcriptionId),
        })

        const targetMediaId = recent?.media_id || transcriptionId
        await transcriptionApi.startTranscription(targetMediaId, {
          mode: 'auto',
          enable_diarization: true,
          transcription_id: transcriptionId,
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
    },
    [activeJobs, activeMeetingTitle, addOrUpdateJob, availableModels, handleCancelTranscription, handleDismissJob, navigate, openStudio, recentTranscriptions, removeJob, setActiveJobs, toast],
  )

  return {
    handleUploadAndStart,
    handleDeleteTranscription,
    handleRetranscribe,
  }
}

