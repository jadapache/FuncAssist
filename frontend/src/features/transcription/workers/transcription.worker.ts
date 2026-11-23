/// <reference lib="webworker" />
import { pipeline, env } from '@huggingface/transformers'
import type {
  AsrProgress,
  AsrRequest,
  AsrSegment,
  WorkerInMessage,
  WorkerOutMessage,
} from '../providers/asrMessages'
import { ASR_SAMPLE_RATE } from '../utils/audioConstants'
import { estimateRemainingSeconds } from '../utils/etaCalculator'
import { formatTimestamp } from '../utils/time'
import { buildCompactAudio, detectSpeechRegions, remapTime } from '../utils/vad'
import { planWindows, segmentsFromWindow, type WhisperChunk } from '../utils/windowMerge'
import { DiarizationCancelled, diarizeSegments } from './diarizer'

// Models come from the Hugging Face Hub and are cached by the browser.
env.allowLocalModels = false

interface ModelProgressInfo {
  status?: string
  progress?: number
  file?: string
  loaded?: number
  total?: number
}

interface TranscriberOutput {
  text?: string
  chunks?: WhisperChunk[]
}

type Transcriber = (audio: Float32Array, options: Record<string, unknown>) => Promise<TranscriberOutput>

const scope = self as unknown as DedicatedWorkerGlobalScope
const post = (message: WorkerOutMessage) => scope.postMessage(message)

let cachedTranscriber: Transcriber | null = null
let cachedModelId = ''
let cachedDevice = ''

/** Loads (or reuses) the Whisper pipeline. `onDownload` receives the 0..1 download progress. */
async function getTranscriber(
  modelId: string,
  onDownload: (fraction: number) => void,
): Promise<{ transcriber: Transcriber; device: string }> {
  if (cachedTranscriber && cachedModelId === modelId) {
    return { transcriber: cachedTranscriber, device: cachedDevice }
  }

  const files = new Map<string, { loaded: number; total: number }>()
  let best = 0
  const progressCallback = (info: ModelProgressInfo) => {
    if (info.status !== 'progress') return
    if (typeof info.loaded === 'number' && typeof info.total === 'number' && info.total > 0) {
      files.set(info.file || 'model', { loaded: info.loaded, total: info.total })
      let loaded = 0
      let total = 0
      for (const item of files.values()) {
        loaded += item.loaded
        total += item.total
      }
      if (total > 0) best = Math.max(best, loaded / total)
    } else if (typeof info.progress === 'number') {
      best = Math.max(best, info.progress / 100)
    }
    onDownload(Math.min(1, best))
  }

  const hasWebGPU =
    typeof navigator !== 'undefined' && 'gpu' in navigator && Boolean((navigator as unknown as { gpu?: unknown }).gpu)
  const attempts: Array<{ device: 'webgpu' | 'wasm'; dtype: unknown; label: string }> = hasWebGPU
    ? [
        { device: 'webgpu', dtype: { encoder_model: 'fp32', decoder_model_merged: 'q4' }, label: 'WebGPU' },
        { device: 'wasm', dtype: 'q4', label: 'CPU Wasm' },
      ]
    : [{ device: 'wasm', dtype: 'q4', label: 'CPU Wasm' }]

  let lastError: unknown = null
  for (const attempt of attempts) {
    try {
      const transcriber = (await pipeline('automatic-speech-recognition', modelId, {
        device: attempt.device as unknown as undefined,
        dtype: attempt.dtype as unknown as undefined,
        progress_callback: progressCallback as unknown as undefined,
      })) as unknown as Transcriber
      cachedTranscriber = transcriber
      cachedModelId = modelId
      cachedDevice = attempt.label
      return { transcriber, device: attempt.label }
    } catch (err) {
      lastError = err
      console.warn(`No se pudo iniciar Whisper con ${attempt.label}:`, err)
    }
  }
  throw lastError instanceof Error ? lastError : new Error('No se pudo cargar el modelo de transcripción.')
}

const cancelled = new Set<string>()

const round2 = (value: number) => Math.round(value * 100) / 100

function progress(payload: AsrProgress) {
  post({ type: 'progress', payload })
}

async function runJob(request: AsrRequest): Promise<void> {
  const { id, audio, language, modelId, duration, diarize = false, numSpeakers = null } = request
  const isCancelled = () => cancelled.has(id)
  const acknowledgeCancel = () => post({ type: 'cancelled', payload: { id } })

  try {
    progress({ id, stage: 'model_download', stageProgress: 0, message: 'Preparando el motor Whisper…' })
    const { transcriber, device } = await getTranscriber(modelId, (fraction) => {
      progress({
        id,
        stage: 'model_download',
        stageProgress: fraction,
        message: `Descargando el modelo (${Math.round(fraction * 100)} %)…`,
      })
    })
    if (isCancelled()) return acknowledgeCancel()
    const modelInfo = `Whisper Web (${device})`

    // Skip long silences: less work and no invented text over silence.
    const regions = detectSpeechRegions(audio, ASR_SAMPLE_RATE)
    if (regions.length === 0) {
      post({
        type: 'complete',
        payload: { id, text: '', segments: [], duration, language, modelInfo, silenceTrimmedSec: duration, diarization: 'none' },
      })
      return
    }
    const { audio: speech, timeMap } = buildCompactAudio(audio, ASR_SAMPLE_RATE, regions)
    const speechSec = speech.length / ASR_SAMPLE_RATE
    const silenceTrimmedSec = Math.max(0, duration - speechSec)
    const windows = planWindows(speechSec)
    const startedAt = performance.now()
    const segments: AsrSegment[] = []
    // Same segments in the speech-only timeline, used to line them up with the diarization.
    const compactSpans: Array<{ start: number; end: number }> = []

    progress({
      id,
      stage: 'transcribing',
      stageProgress: 0,
      message: `Transcribiendo (${formatTimestamp(0)} de ${formatTimestamp(duration)})…`,
      modelInfo,
    })

    for (const win of windows) {
      if (isCancelled()) return acknowledgeCancel()
      const slice = speech.subarray(
        Math.round(win.start * ASR_SAMPLE_RATE),
        Math.round(win.end * ASR_SAMPLE_RATE),
      )
      const output = await transcriber(slice, {
        language: language === 'auto' ? null : language,
        task: 'transcribe',
        return_timestamps: true,
      })
      if (isCancelled()) return acknowledgeCancel()

      const owned = segmentsFromWindow(win, output?.chunks ?? [], output?.text)
      const mapped = owned.map((segment) => ({
        start: round2(remapTime(segment.start, timeMap)),
        end: round2(remapTime(segment.end, timeMap, true)),
        text: segment.text,
      }))
      if (mapped.length > 0) {
        segments.push(...mapped)
        compactSpans.push(...owned.map((segment) => ({ start: segment.start, end: segment.end })))
        post({ type: 'segments', payload: { id, segments: mapped } })
      }

      const processed = Math.min(speechSec, win.isLast ? speechSec : win.ownEnd)
      const elapsedSec = (performance.now() - startedAt) / 1000
      progress({
        id,
        stage: 'transcribing',
        stageProgress: speechSec > 0 ? processed / speechSec : 1,
        message: `Transcribiendo (${formatTimestamp(remapTime(processed, timeMap, true))} de ${formatTimestamp(duration)})…`,
        etaSeconds: estimateRemainingSeconds(processed, speechSec, elapsedSec),
        modelInfo,
      })
      // Let pending messages (cancel) through between windows.
      await new Promise((resolve) => setTimeout(resolve, 0))
    }

    let diarization: 'browser' | 'none' = 'none'
    let diarizationWarning: string | undefined
    if (diarize && segments.length > 0) {
      try {
        const result = await diarizeSegments({
          audio: speech,
          sampleRate: ASR_SAMPLE_RATE,
          segments: compactSpans,
          numSpeakers,
          isCancelled,
          onProgress: (fraction, message) =>
            progress({ id, stage: 'diarizing', stageProgress: fraction, message, modelInfo }),
        })
        result.speakerIds.forEach((speakerId, index) => {
          segments[index].speakerId = speakerId
        })
        diarization = 'browser'
      } catch (error) {
        if (error instanceof DiarizationCancelled || isCancelled()) return acknowledgeCancel()
        // Speakers are optional: keep the transcript with one speaker rather than failing the job.
        console.warn('No se pudieron identificar los interlocutores en el navegador:', error)
        diarizationWarning =
          'No se pudieron identificar los interlocutores en el navegador; la transcripción se guardó con un único interlocutor.'
      }
    }

    post({
      type: 'complete',
      payload: {
        id,
        text: segments.map((segment) => segment.text).join(' ').trim(),
        segments,
        duration,
        language,
        modelInfo,
        silenceTrimmedSec,
        diarization,
        diarizationWarning,
      },
    })
  } catch (error) {
    if (isCancelled()) {
      acknowledgeCancel()
      return
    }
    post({
      type: 'error',
      payload: { id, error: error instanceof Error ? error.message : 'Error durante la transcripción en el navegador.' },
    })
  } finally {
    cancelled.delete(id)
  }
}

scope.onmessage = (event: MessageEvent<WorkerInMessage>) => {
  const message = event.data
  if (message.type === 'cancel') {
    cancelled.add(message.id)
    return
  }
  if (message.type === 'transcribe') {
    void runJob(message.payload)
  }
}
