import { Injectable, inject, type Signal } from '@angular/core'
import { Router } from '@angular/router'
import type { BackgroundJobItem } from '../../../core/jobs/background-job.service'
import type { ToastService } from '../../../core/notifications/toast.service'
import {
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionProgress,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { runClientTranscription, resolveClientOnnxModel } from '../utils/clientTranscription'
import type { RefObject, SetStateAction } from '../utils/reactCompat'
import type { TranscriptionViewMode } from './transcription-modals.service'

export interface PipelineProps {
  availableModels: Signal<AvailableModelsInfo | null>
  activeJobs: Signal<Record<string, TranscriptionProgress>>
  setActiveJobs: (action: SetStateAction<Record<string, TranscriptionProgress>>) => void
  recentTranscriptions: Signal<TranscriptionResult[]>
  setRecentTranscriptions: (action: SetStateAction<TranscriptionResult[]>) => void
  setIsUploading: (val: boolean) => void
  openStudio: (id: string, title?: string) => void
  setActiveMeetingTitle: (title: string) => void
  setSelectedTranscriptionId: (id: string | null) => void
  selectedTranscriptionId: Signal<string | null>
  activeMeetingTitle: Signal<string>
  setViewMode: (action: SetStateAction<TranscriptionViewMode>) => void
  addOrUpdateJob: (job: BackgroundJobItem) => void
  removeJob: (id: string) => void
  handleCancelTranscription: (id: string) => Promise<void>
  handleDismissJob: (id: string) => void
  toast: ToastService['toast']
  abortControllersRef: RefObject<Record<string, AbortController>>
  cancelledJobsRef: RefObject<Set<string>>
  activeWorkersRef: RefObject<Record<string, Worker>>
  clientJobIdsRef: RefObject<Set<string>>
}

/**
 * Angular port of React `useTranscriptionPipeline`.
 *
 * Global (root) service: React only used this hook inside `TranscriptionProvider`. The hook props
 * arrive through {@link configure}, called once by `TranscriptionStore`.
 */
@Injectable({ providedIn: 'root' })
export class TranscriptionPipelineService {
  private readonly router = inject(Router)
  private props!: PipelineProps

  /** Receives the React hook props. Must be called once (by `TranscriptionStore`). */
  configure(props: PipelineProps): void {
    this.props = props
  }

  private jobClickHandler(transcriptionId: string): () => void {
    return () => {
      this.props.openStudio(transcriptionId)
      void this.router.navigateByUrl('/transcripciones')
    }
  }

  private async executeClientAudioPath(
    transcriptionId: string,
    file: File,
    title: string,
    description: string,
  ): Promise<void> {
    const {
      availableModels,
      setActiveJobs,
      setRecentTranscriptions,
      setSelectedTranscriptionId,
      setViewMode,
      addOrUpdateJob,
      handleCancelTranscription,
      handleDismissJob,
      toast,
      cancelledJobsRef,
      activeWorkersRef,
      clientJobIdsRef,
    } = this.props

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
      onClick: this.jobClickHandler(transcriptionId),
      onCancel: () => void handleCancelTranscription(transcriptionId),
      onDismiss: () => handleDismissJob(transcriptionId),
    })

    const modelId = resolveClientOnnxModel(availableModels()?.configured_model)
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
          onClick: this.jobClickHandler(transcriptionId),
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

    setRecentTranscriptions((prev) => [result.transcription, ...prev.filter((t) => t.id !== transcriptionId)])
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
      onClick: this.jobClickHandler(transcriptionId),
      onDismiss: () => handleDismissJob(transcriptionId),
    })
    toast.success('Transcripción completada con éxito.')
    setViewMode('studio')
  }

  private async executeUploadAndServerPath(
    transcriptionId: string,
    file: File,
    title: string,
    description: string,
  ): Promise<void> {
    const {
      availableModels,
      setActiveJobs,
      setSelectedTranscriptionId,
      setViewMode,
      addOrUpdateJob,
      handleCancelTranscription,
      handleDismissJob,
      abortControllersRef,
      cancelledJobsRef,
    } = this.props

    setSelectedTranscriptionId(transcriptionId)
    const initJob: TranscriptionProgress = {
      id: transcriptionId,
      media_id: transcriptionId,
      title,
      status: 'preprocessing',
      stage: 'preprocessing',
      progress: 5,
      message: 'Extrayendo y procesando audio en el navegador...',
      eta: null,
      model_info: availableModels()?.active_model_label || 'Whisper Cloud',
    }
    setActiveJobs((prev) => ({ ...prev, [transcriptionId]: initJob }))
    addOrUpdateJob({
      id: transcriptionId,
      type: 'transcription',
      title,
      progress: 5,
      status: 'preprocessing',
      stageText: 'Procesando audio...',
      eta: null,
      onClick: this.jobClickHandler(transcriptionId),
      onCancel: () => void handleCancelTranscription(transcriptionId),
      onDismiss: () => handleDismissJob(transcriptionId),
    })

    const payloadToUpload: File | Blob = file
    const uploadFilename = file.name

    if (cancelledJobsRef.current.has(transcriptionId)) return

    setActiveJobs((prev) => {
      if (!prev[transcriptionId]) return prev
      return {
        ...prev,
        [transcriptionId]: {
          ...prev[transcriptionId],
          status: 'uploading',
          stage: 'uploading',
          progress: 20,
          message: 'Enviando audio al servidor para transcripción en la nube...',
        },
      }
    })

    const uploadRes = await transcriptionApi.uploadMediaFile(
      payloadToUpload,
      title,
      description,
      transcriptionId,
      uploadFilename,
    )
    const mediaId = uploadRes.media_id || transcriptionId

    delete abortControllersRef.current[transcriptionId]
    if (cancelledJobsRef.current.has(transcriptionId)) return

    const preprocessingJob: TranscriptionProgress = {
      id: transcriptionId,
      media_id: mediaId,
      title,
      status: 'preprocessing',
      stage: 'preprocessing',
      progress: 15,
      message: 'Procesando archivo en el servidor...',
      eta: null,
      model_info: availableModels()?.active_model_label || 'Whisper Cloud',
    }
    setActiveJobs((prev) => {
      if (cancelledJobsRef.current.has(transcriptionId)) return prev
      return { ...prev, [transcriptionId]: preprocessingJob }
    })
    addOrUpdateJob({
      id: transcriptionId,
      type: 'transcription',
      title,
      progress: 15,
      status: 'preprocessing',
      stageText: 'Procesando archivo en el servidor...',
      eta: null,
      onClick: this.jobClickHandler(transcriptionId),
      onCancel: () => void handleCancelTranscription(transcriptionId),
      onDismiss: () => handleDismissJob(transcriptionId),
    })

    await transcriptionApi.startTranscription(mediaId, {
      transcription_id: transcriptionId,
      mode: 'auto',
      enable_diarization: true,
    })

    if (!cancelledJobsRef.current.has(transcriptionId)) {
      setViewMode('studio')
    }
  }

  private async executeServerAudioPath(
    transcriptionId: string,
    localPath: string,
    title: string,
    description: string,
  ): Promise<void> {
    const {
      availableModels,
      setActiveJobs,
      setSelectedTranscriptionId,
      setViewMode,
      addOrUpdateJob,
      handleCancelTranscription,
      handleDismissJob,
      abortControllersRef,
      cancelledJobsRef,
    } = this.props

    const regRes = await transcriptionApi.registerLocalPath(localPath.trim(), title, description, transcriptionId)
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
      model_info: availableModels()?.active_model_label || 'Whisper Auto',
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
      onClick: this.jobClickHandler(transcriptionId),
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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async handleUploadAndStart(target: any, title: string, description: string = ''): Promise<void> {
    const {
      availableModels,
      setActiveJobs,
      setIsUploading,
      setActiveMeetingTitle,
      removeJob,
      toast,
      abortControllersRef,
      cancelledJobsRef,
      clientJobIdsRef,
    } = this.props

    const transcriptionId =
      typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `trans_${Date.now()}`

    cancelledJobsRef.current.delete(transcriptionId)
    abortControllersRef.current[transcriptionId] = new AbortController()
    const localPath = (target?.path || target?.filePath || '') as string

    try {
      setIsUploading(true)
      setActiveMeetingTitle(title)

      if (!localPath && target instanceof File) {
        const models = availableModels()
        const isCloud =
          models?.configured_provider === 'groq' ||
          models?.configured_provider === 'openai' ||
          models?.configured_provider === 'cloud'

        if (isCloud) {
          await this.executeUploadAndServerPath(transcriptionId, target, title, description)
          return
        }

        await this.executeClientAudioPath(transcriptionId, target, title, description)
        return
      }

      if (!localPath || typeof localPath !== 'string' || localPath.trim().length === 0) {
        throw new Error('No se pudo resolver la ruta local del archivo multimedia.')
      }

      await this.executeServerAudioPath(transcriptionId, localPath, title, description)
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
  }

  async handleDeleteTranscription(transcriptionId: string): Promise<void> {
    const {
      setRecentTranscriptions,
      setActiveJobs,
      removeJob,
      selectedTranscriptionId,
      setViewMode,
      setSelectedTranscriptionId,
      toast,
    } = this.props
    try {
      await transcriptionApi.deleteTranscription(transcriptionId)
      setRecentTranscriptions((prev) => prev.filter((t) => t.id !== transcriptionId))
      setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })
      removeJob(transcriptionId)
      if (selectedTranscriptionId() === transcriptionId) {
        setViewMode('dashboard')
        setSelectedTranscriptionId(null)
      }
      toast.success('Transcripción eliminada con éxito.')
    } catch (err: unknown) {
      toast.error(`Error al eliminar: ${(err as Error)?.message}`)
    }
  }

  async handleRetranscribe(transcriptionId: string, title?: string): Promise<void> {
    const {
      activeJobs,
      recentTranscriptions,
      activeMeetingTitle,
      availableModels,
      setActiveJobs,
      addOrUpdateJob,
      handleCancelTranscription,
      handleDismissJob,
      removeJob,
      toast,
    } = this.props
    try {
      const active = activeJobs()[transcriptionId]
      const recent = recentTranscriptions().find((t) => t.id === transcriptionId)
      const jobTitle = title || active?.title || recent?.metadata?.title || activeMeetingTitle() || 'Transcripción'

      const retransJob: TranscriptionProgress = {
        id: transcriptionId,
        media_id: recent?.media_id || '',
        title: jobTitle,
        status: 'preprocessing',
        stage: 'preprocessing',
        progress: 0,
        message: 'Iniciando regeneración con el motor configurado...',
        eta: null,
        model_info: availableModels()?.active_model_label || 'Whisper Auto',
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
        onClick: this.jobClickHandler(transcriptionId),
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
    } catch (err: unknown) {
      toast.error(`Error al regenerar transcripción: ${(err as Error)?.message}`)
      setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })
      removeJob(transcriptionId)
    }
  }
}
