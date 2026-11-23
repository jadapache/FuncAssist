import { useCallback, useRef, type Dispatch } from 'react'
import {
  errorStatus,
  isAbortError,
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import type { JobsAction, JobsState } from '../context/transcriptionJobs'
import { browserAsrProvider } from '../providers/BrowserAsrProvider'
import { runBrowserTranscription } from '../utils/clientTranscription'
import { generateTranscriptSummary } from '../utils/summary'
import {
  BROWSER_STAGE_RANGES,
  SERVER_STAGE_RANGES,
  isTerminalStage,
  overallProgress,
} from '../utils/transcriptionStages'
import { useLatest } from './useLatest'

/** Per-job options chosen in the upload form. `vocabulary` only applies to server jobs. */
export interface UploadJobOptions {
  diarize?: boolean
  numSpeakers?: number | null
  vocabulary?: string
}

export interface ToastApi {
  success: (message: string, title?: string) => unknown
  error: (message: string, title?: string) => unknown
  warning: (message: string, title?: string) => unknown
  info: (message: string, title?: string) => unknown
}

interface RunnerDeps {
  dispatch: Dispatch<JobsAction>
  jobsRef: { readonly current: JobsState }
  availableModels: AvailableModelsInfo | null
  toast: ToastApi
  /** A saved record (new transcription or updated summary) to merge into the list. */
  onRecordSaved: (record: TranscriptionResult) => void
  /** Called once a job is created, to show it. */
  onJobCreated: (id: string, title: string) => void
}

const CLOUD_PROVIDERS = new Set(['groq', 'openai', 'cloud'])

export function isCloudTranscriptionProvider(models: AvailableModelsInfo | null): boolean {
  return CLOUD_PROVIDERS.has((models?.configured_provider || '').toLowerCase())
}

function newJobId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `trans_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`
}

const errorMessage = (err: unknown, fallback: string) => (err instanceof Error && err.message ? err.message : fallback)

/** Starts, cancels and retries transcription jobs. State lives in the jobs reducer. */
export function useTranscriptionJobRunners(deps: RunnerDeps) {
  const depsRef = useLatest(deps)
  const controllersRef = useRef(new Map<string, AbortController>())
  const cancelledRef = useRef(new Set<string>())

  const startServerJob = useCallback(
    async (file: File, title: string, description: string, options: UploadJobOptions) => {
      const { dispatch, availableModels, onJobCreated } = depsRef.current
      const id = newJobId()
      const controller = new AbortController()
      controllersRef.current.set(id, controller)
      dispatch({
        type: 'start',
        job: {
          id,
          kind: 'server',
          title,
          stage: 'uploading',
          progress: 0,
          message: 'Subiendo archivo…',
          model_info: availableModels?.active_model_label || null,
        },
      })
      onJobCreated(id, title)

      try {
        const upload = await transcriptionApi.uploadMediaFile(file, title, description, id, file.name, {
          signal: controller.signal,
          onProgress: (loaded, total) => {
            const fraction = total > 0 ? loaded / total : 0
            depsRef.current.dispatch({
              type: 'update',
              id,
              patch: {
                stage: 'uploading',
                progress: overallProgress('uploading', fraction, SERVER_STAGE_RANGES),
                stage_progress: fraction,
                message: `Subiendo archivo (${Math.round(fraction * 100)} %)…`,
              },
            })
          },
        })
        if (cancelledRef.current.has(id)) return

        await transcriptionApi.startTranscription(upload.media_id || id, {
          transcription_id: id,
          diarize: options.diarize ?? true,
          num_speakers: options.numSpeakers || undefined,
          vocabulary: options.vocabulary?.trim() || undefined,
        })
        if (cancelledRef.current.has(id)) {
          // Cancelled while the job was being created: stop it on the server too.
          await transcriptionApi.cancelTranscription(id).catch(() => undefined)
          return
        }
        // From here the progress stream follows the job.
        depsRef.current.dispatch({
          type: 'update',
          id,
          patch: { stage: 'queued', progress: SERVER_STAGE_RANGES.queued?.[0] ?? 10, message: 'Archivo recibido. En cola…' },
        })
      } catch (err) {
        if (isAbortError(err) || cancelledRef.current.has(id)) {
          depsRef.current.dispatch({ type: 'update', id, patch: { stage: 'cancelled' } })
          return
        }
        const status = errorStatus(err)
        depsRef.current.dispatch({
          type: 'update',
          id,
          patch: {
            stage: 'failed',
            error: errorMessage(err, 'No se pudo subir el archivo.'),
            error_code: status === 413 ? 'file_too_large' : 'upload_failed',
            retryable: false,
          },
        })
      } finally {
        controllersRef.current.delete(id)
      }
    },
    [depsRef],
  )

  const startBrowserJob = useCallback(
    async (file: File, title: string, description: string, options: UploadJobOptions = {}) => {
      const { dispatch, availableModels, onJobCreated } = depsRef.current
      const id = newJobId()
      const controller = new AbortController()
      controllersRef.current.set(id, controller)
      dispatch({
        type: 'start',
        job: { id, kind: 'browser', title, stage: 'decoding', progress: 0, message: 'Preparando el audio…', model_info: 'Whisper Web' },
      })
      onJobCreated(id, title)

      let saved: TranscriptionResult | null = null
      try {
        saved = await runBrowserTranscription({
          id,
          file,
          title,
          description,
          modelId: availableModels?.configured_model,
          signal: controller.signal,
          diarize: options.diarize ?? availableModels?.browser_diarization ?? false,
          numSpeakers: options.numSpeakers ?? null,
          onWarning: (message) => depsRef.current.toast.warning(message, 'Interlocutores'),
          onStage: (update) =>
            depsRef.current.dispatch({
              type: 'update',
              id,
              patch: {
                stage: update.stage,
                stage_progress: update.stageProgress,
                progress: overallProgress(update.stage, update.stageProgress, BROWSER_STAGE_RANGES),
                message: update.message,
                eta_seconds: update.etaSeconds ?? null,
                ...(update.modelInfo ? { model_info: update.modelInfo } : {}),
              },
            }),
          onSegments: (segments) => depsRef.current.dispatch({ type: 'append_segments', id, segments }),
        })
      } catch (err) {
        if (isAbortError(err) || cancelledRef.current.has(id)) {
          depsRef.current.dispatch({ type: 'update', id, patch: { stage: 'cancelled' } })
        } else {
          depsRef.current.dispatch({
            type: 'update',
            id,
            patch: { stage: 'failed', error: errorMessage(err, 'Error durante la transcripción en el navegador.'), retryable: false },
          })
        }
        return
      } finally {
        controllersRef.current.delete(id)
      }

      if (!saved) return
      depsRef.current.onRecordSaved(saved)
      depsRef.current.dispatch({ type: 'update', id, patch: { stage: 'complete', summary_status: 'running' } })
      try {
        const withSummary = await generateTranscriptSummary({ transcriptionId: id, title, record: saved })
        depsRef.current.onRecordSaved(withSummary)
        depsRef.current.dispatch({ type: 'update', id, patch: { summary_status: 'done' } })
      } catch (err) {
        depsRef.current.dispatch({ type: 'update', id, patch: { summary_status: 'failed' } })
        depsRef.current.toast.warning(
          errorMessage(err, 'Puedes generarlo desde la transcripción.'),
          'La transcripción se guardó, pero no se pudo generar el resumen',
        )
      }
    },
    [depsRef],
  )

  const cancel = useCallback(
    async (id: string) => {
      const { jobsRef, dispatch, toast } = depsRef.current
      const job = jobsRef.current[id]
      if (!job || isTerminalStage(job.stage)) return
      cancelledRef.current.add(id)
      const controller = controllersRef.current.get(id)

      if (job.kind === 'browser' || job.stage === 'uploading') {
        controller?.abort()
        if (job.kind === 'browser') browserAsrProvider.cancel(id)
        dispatch({ type: 'update', id, patch: { stage: 'cancelled' } })
        toast.info('Transcripción cancelada.')
        return
      }

      dispatch({ type: 'update', id, patch: { message: 'Cancelando…' } })
      try {
        await transcriptionApi.cancelTranscription(id)
        dispatch({ type: 'update', id, patch: { stage: 'cancelled' } })
        toast.info('Transcripción cancelada.')
      } catch (err) {
        cancelledRef.current.delete(id)
        toast.error(errorMessage(err, 'Error desconocido.'), 'No se pudo cancelar la transcripción')
      }
    },
    [depsRef],
  )

  /** Resumes a failed or interrupted server job from its saved chunks. */
  const retry = useCallback(
    async (id: string, title?: string) => {
      const { jobsRef, dispatch, toast, onJobCreated } = depsRef.current
      const jobTitle = title || jobsRef.current[id]?.title || 'Transcripción'
      cancelledRef.current.delete(id)
      try {
        await transcriptionApi.retryTranscription(id)
        dispatch({
          type: 'start',
          job: { id, kind: 'server', title: jobTitle, stage: 'queued', progress: 10, message: 'Reintentando…' },
        })
        onJobCreated(id, jobTitle)
      } catch (err) {
        toast.error(errorMessage(err, 'Error desconocido.'), 'No se pudo reintentar la transcripción')
      }
    },
    [depsRef],
  )

  /** Transcribes again a record whose media is on the server. */
  const regenerate = useCallback(
    async (record: Pick<TranscriptionResult, 'id' | 'media_id' | 'metadata'>, options: UploadJobOptions = {}) => {
      const { dispatch, toast, availableModels, onJobCreated } = depsRef.current
      const title = record.metadata?.title || 'Transcripción'
      cancelledRef.current.delete(record.id)
      try {
        await transcriptionApi.startTranscription(record.media_id || record.id, {
          transcription_id: record.id,
          diarize: options.diarize ?? true,
          num_speakers: options.numSpeakers || undefined,
          vocabulary: options.vocabulary?.trim() || undefined,
        })
        dispatch({
          type: 'start',
          job: {
            id: record.id,
            kind: 'server',
            title,
            stage: 'queued',
            progress: 10,
            message: 'Regeneración en cola…',
            model_info: availableModels?.active_model_label || null,
          },
        })
        onJobCreated(record.id, title)
      } catch (err) {
        toast.error(errorMessage(err, 'Error desconocido.'), 'No se pudo regenerar la transcripción')
      }
    },
    [depsRef],
  )

  return { startServerJob, startBrowserJob, cancel, retry, regenerate }
}
