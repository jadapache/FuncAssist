import { extractAudioTrackFromMedia } from './audioExtractor'
import {
  transcriptionApi,
  type TranscriptionResult,
  type TranscriptionSummary,
} from '../api/transcriptionApi'

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
  if (!configuredModel) return 'onnx-community/whisper-tiny'
  const lower = configuredModel.toLowerCase()
  if (lower.includes('base')) return 'onnx-community/whisper-base'
  if (lower.includes('small')) return 'onnx-community/whisper-small'
  if (lower.includes('large')) return 'onnx-community/whisper-large-v3-turbo'
  if (lower.includes('tiny')) return 'onnx-community/whisper-tiny'
  if (lower.startsWith('onnx-community/') || lower.includes('/')) return configuredModel
  return 'onnx-community/whisper-tiny'
}

/**
 * Orchestrates client-side audio extraction and in-browser transcription via Web Worker.
 * Submits the lightweight transcript text to the backend for functional summarization.
 */
export async function runClientTranscription(
  options: ClientTranscriptionOptions
): Promise<ClientTranscriptionResult> {
  const {
    id,
    file,
    title,
    description = '',
    language = 'es',
    modelId = 'onnx-community/whisper-base',
    onProgress,
    onRegisterWorker,
    isCancelled,
  } = options

  // 1. Audio Extraction in browser memory
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
      onProgress({
        progress: progressPct,
        stage: 'preprocessing',
        message,
      })
    }
  )

  if (isCancelled()) {
    throw new Error('Transcripción cancelada por el usuario.')
  }

  // 2. Transcribing with Web Worker (WebGPU / CPU Wasm)
  const worker = new Worker(
    new URL('../workers/transcription.worker.ts', import.meta.url),
    { type: 'module' }
  )
  onRegisterWorker?.(worker)

  const workerResult = await new Promise<{
    text: string
    segments: ClientTranscriptionSegment[]
    duration: number
    language: string
    model_info: string
  }>((resolve, reject) => {
    worker.onmessage = (e: MessageEvent) => {
      if (isCancelled()) {
        worker.terminate()
        reject(new Error('Transcripción cancelada por el usuario.'))
        return
      }

      const { type, payload } = e.data
      if (type === 'progress') {
        onProgress({
          progress: payload.progress,
          stage: 'transcribing',
          message: payload.message,
          eta: payload.eta,
          live_text: payload.live_text,
          live_segments: payload.live_segments,
          model_info: payload.model_info,
        })
      } else if (type === 'complete') {
        worker.terminate()
        resolve(payload)
      } else if (type === 'error') {
        worker.terminate()
        reject(new Error(payload.error || 'Error durante la inferencia en navegador.'))
      }
    }

    worker.onerror = (err) => {
      worker.terminate()
      reject(err)
    }

    worker.postMessage({
      type: 'transcribe',
      payload: {
        id,
        audioData,
        language,
        modelId,
        duration,
      },
    })
  })

  if (isCancelled()) {
    throw new Error('Transcripción cancelada por el usuario.')
  }

  // 3. Submit lightweight transcript to SaaS backend for summarization
  onProgress({
    progress: 92,
    stage: 'summarizing',
    message: 'Generando resumen con IA...',
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
    generate_summary_now: true,
  })

  if (!submitResponse.ok || !submitResponse.transcription) {
    throw new Error('Error al registrar la transcripción en la plataforma.')
  }

  return {
    transcription: submitResponse.transcription,
    summary: submitResponse.summary,
  }
}
