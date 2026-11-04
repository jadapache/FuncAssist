import { extractAudioTrackFromMedia } from './audioExtractor'
import {
  transcriptionApi,
  type TranscriptionResult,
  type TranscriptionSummary,
} from '../api/transcriptionApi'
import {
  browserAsrProvider,
} from '../providers/BrowserAsrProvider'
import {
  DEFAULT_BROWSER_ASR_MODEL,
  isSupportedBrowserAsrModel,
} from '../../ai/catalogs/clientCatalog'
import { inferenceService } from '../../ai/services/InferenceService'

export interface ClientTranscriptionSegment {
  start: number
  end: number
  speaker: string
  text: string
}

export interface ClientProgressUpdate {
  progress: number
  stage: 'preprocessing' | 'transcribing' | 'summarizing'
  message: string
  eta?: string | null
  live_text?: string
  live_segments?: ClientTranscriptionSegment[]
  model_info?: string
}

export interface ClientTranscriptionOptions {
  id: string
  file: File
  title: string
  description?: string
  language?: string
  modelId?: string
  onProgress: (data: ClientProgressUpdate) => void
  onRegisterWorker?: (worker: Worker) => void
  isCancelled: () => boolean
}

export interface ClientTranscriptionResult {
  transcription: TranscriptionResult
  summary?: TranscriptionSummary
}

export function resolveClientOnnxModel(configuredModel?: string): string {
  if (!configuredModel) return DEFAULT_BROWSER_ASR_MODEL
  if (isSupportedBrowserAsrModel(configuredModel)) return configuredModel
  return DEFAULT_BROWSER_ASR_MODEL
}

async function generateBrowserSummary(title: string, text: string): Promise<TranscriptionSummary | undefined> {
  try {
    const summaryResult = await inferenceService.summarize({
      text,
      instructions: `Genera un resumen ejecutivo estructurado para la reunión titulada "${title}".`,
      maxTokens: 1024,
      temperature: 0.3,
    })
    return {
      summary_text: summaryResult.summary,
      topics: [title],
    }
  } catch {
    return undefined
  }
}

export async function runClientTranscription(
  options: ClientTranscriptionOptions,
): Promise<ClientTranscriptionResult> {
  const {
    id,
    file,
    title,
    description = '',
    language = 'es',
    modelId = DEFAULT_BROWSER_ASR_MODEL,
    onProgress,
    onRegisterWorker,
    isCancelled,
  } = options

  onProgress({
    progress: 1,
    stage: 'preprocessing',
    message: 'Extrayendo audio...',
    model_info: 'Whisper Web (Client)',
  })

  const { audioData, duration } = await extractAudioTrackFromMedia(
    file,
    16000,
    (progressPct, message) => {
      if (isCancelled()) return
      onProgress({ progress: progressPct, stage: 'preprocessing', message })
    },
  )

  if (isCancelled()) {
    throw new Error('Transcripción cancelada por el usuario.')
  }

  const effectiveModelId = resolveClientOnnxModel(modelId)
  const workerResult = await browserAsrProvider.transcribe(
    {
      id,
      audioData,
      language,
      modelId: effectiveModelId,
      duration,
    },
    (update) => {
      onProgress({
        progress: update.progress,
        stage: 'transcribing',
        message: update.message,
        eta: update.eta,
        live_text: update.live_text,
        live_segments: update.live_segments,
        model_info: update.model_info,
      })
    },
    isCancelled,
    onRegisterWorker,
  )

  if (isCancelled()) {
    throw new Error('Transcripción cancelada por el usuario.')
  }

  onProgress({
    progress: 92,
    stage: 'summarizing',
    message: 'Registrando transcripción en el sistema...',
    model_info: workerResult.model_info,
  })

  const submitResponse = await transcriptionApi.submitClientTranscription({
    id,
    title,
    description,
    text: workerResult.text,
    segments: workerResult.segments,
    duration_seconds: workerResult.duration,
    language: workerResult.language,
    generate_summary_now: false,
  })

  if (!submitResponse.ok || !submitResponse.transcription) {
    throw new Error('Error al registrar la transcripción en la plataforma.')
  }

  const generatedSummary = await generateBrowserSummary(title, workerResult.text)
  if (generatedSummary) {
    await transcriptionApi.updateTranscriptionSummary(id, generatedSummary).catch(() => null)
  }

  return {
    transcription: {
      ...submitResponse.transcription,
      summary: generatedSummary || submitResponse.transcription.summary,
    },
    summary: generatedSummary,
  }
}
