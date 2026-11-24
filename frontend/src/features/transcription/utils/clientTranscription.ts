import {
  transcriptionApi,
  type TranscriptionResult,
  type TranscriptionSegment,
  type TranscriptionStage,
} from '../api/transcriptionApi'
import { releaseOtherGpuConsumers } from '../../../core/gpu/gpuResources'
import { ASR_GPU_CONSUMER, browserAsrProvider, type AsrSegment } from '../providers/BrowserAsrProvider'
import { DEFAULT_BROWSER_ASR_MODEL, isSupportedBrowserAsrModel } from '../../ai/catalogs/clientCatalog'
import { throwIfAborted } from './abort'
import { decodeMediaFile } from './audioDecode'

export interface BrowserStageUpdate {
  stage: TranscriptionStage
  stageProgress: number
  message: string
  etaSeconds?: number | null
  modelInfo?: string
}

export interface BrowserTranscriptionOptions {
  id: string
  file: File
  title: string
  description?: string
  language?: string
  modelId?: string
  signal: AbortSignal
  diarize?: boolean
  numSpeakers?: number | null
  consentConfirmed: boolean
  onStage: (update: BrowserStageUpdate) => void
  onSegments: (segments: TranscriptionSegment[]) => void
  /** Non-fatal problems, e.g. speakers could not be identified. */
  onWarning?: (message: string) => void
}

export function resolveClientOnnxModel(configuredModel?: string | null): string {
  if (configuredModel && isSupportedBrowserAsrModel(configuredModel)) return configuredModel
  return DEFAULT_BROWSER_ASR_MODEL
}

/** Live segments have no speaker yet; diarized results carry S1, S2… from the worker. */
function toSegment(segment: AsrSegment): TranscriptionSegment {
  const speakerId = segment.speakerId || 'S1'
  const number = Number.parseInt(speakerId.slice(1), 10) || 1
  return {
    start: segment.start,
    end: segment.end,
    speaker: `Participante ${number}`,
    speaker_id: speakerId,
    text: segment.text,
  }
}

/**
 * Decode → Whisper (and optionally speaker identification) in the worker → save. The backend
 * applies the rule-based cleanup when it stores the verbatim result. The summary is generated
 * afterwards by the caller.
 */
export async function runBrowserTranscription(options: BrowserTranscriptionOptions): Promise<TranscriptionResult> {
  const {
    id,
    file,
    title,
    description = '',
    language = 'es',
    modelId,
    signal,
    diarize = false,
    numSpeakers = null,
    consentConfirmed,
    onStage,
    onSegments,
    onWarning,
  } = options
  if (!consentConfirmed) {
    throw new Error('Debes confirmar la autorización de los participantes (Ley 1581 de 2012) antes de transcribir.')
  }

  onStage({ stage: 'decoding', stageProgress: 0, message: 'Preparando el audio…' })
  const { samples, duration } = await decodeMediaFile(file, {
    signal,
    onProgress: (fraction, message) => onStage({ stage: 'decoding', stageProgress: fraction, message }),
  })
  throwIfAborted(signal)

  // Whisper may run on the GPU: unload an idle in-browser LLM first so both do not compete for VRAM.
  await releaseOtherGpuConsumers(ASR_GPU_CONSUMER)
  const result = await browserAsrProvider.transcribe(
    { id, audio: samples, language, modelId: resolveClientOnnxModel(modelId), duration, diarize, numSpeakers },
    {
      onProgress: (update) =>
        onStage({
          stage: update.stage,
          stageProgress: update.stageProgress,
          message: update.message,
          etaSeconds: update.etaSeconds,
          modelInfo: update.modelInfo,
        }),
      onSegments: (segments) => onSegments(segments.map(toSegment)),
    },
    signal,
  )
  throwIfAborted(signal)
  if (result.diarizationWarning) onWarning?.(result.diarizationWarning)

  onStage({ stage: 'saving', stageProgress: 0, message: 'Guardando la transcripción…', modelInfo: result.modelInfo })
  const response = await transcriptionApi.submitClientTranscription({
    id,
    title,
    description,
    text: result.text,
    segments: result.segments.map(toSegment),
    duration_seconds: result.duration,
    language: result.language,
    generate_summary_now: false,
    diarization: result.diarization,
    consent_confirmed: consentConfirmed,
  })
  if (!response?.ok || !response.transcription) {
    throw new Error('No se pudo registrar la transcripción en la plataforma.')
  }
  return response.transcription
}
