/// <reference lib="webworker" />
import { pipeline, env } from '@huggingface/transformers'
import { EtaTracker, formatAudioTime } from '../utils/etaCalculator'

// Allow remote model loading via Hugging Face Hub (cached automatically in browser storage)
env.allowLocalModels = false

interface ProgressInfo {
  status?: string
  progress?: number
  file?: string
}

interface WorkerTranscriberResult {
  text?: string
  chunks?: Array<{
    text?: string
    timestamp?: [number | null, number | null]
  }>
}

type TranscriberFn = (
  audioData: Float32Array,
  options: Record<string, unknown>
) => Promise<WorkerTranscriberResult>

let activeTranscriber: TranscriberFn | null = null
let currentModelId = ''
let currentDevice = ''

async function getTranscriber(
  modelId: string = 'onnx-community/whisper-base',
  onProgress?: (data: ProgressInfo) => void
): Promise<{ transcriber: TranscriberFn; device: string }> {
  // Return cached pipeline instance if already loaded with same model
  if (activeTranscriber && currentModelId === modelId) {
    return { transcriber: activeTranscriber, device: currentDevice }
  }

  // Detect WebGPU availability in worker
  const hasWebGPU = typeof navigator !== 'undefined' && 'gpu' in navigator && !!(navigator as unknown as { gpu?: unknown }).gpu
  const preferredDevice = hasWebGPU ? 'webgpu' : 'wasm'

  const webGpuDtype = {
    encoder_model: 'fp32',
    decoder_model_merged: 'q4',
  }
  const wasmDtype = 'q4'

  try {
    const transcriber = (await pipeline('automatic-speech-recognition', modelId, {
      device: preferredDevice as unknown as undefined,
      dtype: (preferredDevice === 'webgpu' ? webGpuDtype : wasmDtype) as unknown as undefined,
      progress_callback: (info: ProgressInfo) => {
        if (info.status === 'progress' && onProgress) {
          onProgress(info)
        }
      },
    })) as unknown as TranscriberFn

    activeTranscriber = transcriber
    currentModelId = modelId
    currentDevice = preferredDevice === 'webgpu' ? 'WebGPU' : 'CPU Wasm'
    return { transcriber, device: currentDevice }
  } catch (err) {
    console.warn('Pipeline initialization failed on preferred device, attempting fallback to wasm/q4:', err)
    // If WebGPU failed or threw, fall back to wasm CPU execution with q4
    if (preferredDevice === 'webgpu') {
      const transcriber = (await pipeline('automatic-speech-recognition', modelId, {
        device: 'wasm' as unknown as undefined,
        dtype: wasmDtype as unknown as undefined,
        progress_callback: onProgress,
      })) as unknown as TranscriberFn

      activeTranscriber = transcriber
      currentModelId = modelId
      currentDevice = 'CPU Wasm'
      return { transcriber, device: currentDevice }
    }
    throw err
  }
}

self.onmessage = async (event: MessageEvent) => {
  const { type, payload } = event.data

  if (type !== 'transcribe') return

  const {
    id,
    audioData,
    language = 'es',
    modelId = 'onnx-community/whisper-base',
    duration = 0,
  } = payload

  try {
    self.postMessage({
      type: 'progress',
      payload: {
        id,
        progress: 10,
        stage: 'transcribing',
        message: 'Preparando motor Whisper...',
      },
    })

    let maxDownloadPercent = 0
    const fileBytesMap = new Map<string, { loaded: number; total: number }>()

    const { transcriber, device } = await getTranscriber(modelId, (progressInfo: ProgressInfo) => {
      if (progressInfo && typeof progressInfo.progress === 'number') {
        const fileKey = progressInfo.file || 'model_part'
        const loaded = (progressInfo as unknown as { loaded?: number }).loaded
        const total = (progressInfo as unknown as { total?: number }).total

        if (typeof loaded === 'number' && typeof total === 'number' && total > 0) {
          fileBytesMap.set(fileKey, { loaded, total })
          let sumLoaded = 0
          let sumTotal = 0
          for (const item of fileBytesMap.values()) {
            sumLoaded += item.loaded
            sumTotal += item.total
          }
          if (sumTotal > 0) {
            const overallPct = Math.round((sumLoaded / sumTotal) * 100)
            maxDownloadPercent = Math.max(maxDownloadPercent, overallPct)
          }
        } else {
          maxDownloadPercent = Math.max(maxDownloadPercent, Math.round(progressInfo.progress))
        }

        const downloadPct = 10 + Math.round((maxDownloadPercent / 100) * 10)
        self.postMessage({
          type: 'progress',
          payload: {
            id,
            progress: downloadPct,
            stage: 'transcribing',
            message: `Descargando componentes (${maxDownloadPercent}%)...`,
          },
        })
      }
    })

    self.postMessage({
      type: 'progress',
      payload: {
        id,
        progress: 20,
        stage: 'transcribing',
        message: duration > 0 ? `Iniciando decodificación (${formatAudioTime(duration)})...` : 'Iniciando decodificación...',
        model_info: `Whisper Web (${device})`,
      },
    })

    const liveSegments: Array<{ start: number; end: number; speaker: string; text: string }> = []
    let accumulatedText = ''
    const etaTracker = new EtaTracker()
    etaTracker.start()

    // Process audio in 30-second windows so long files update progress, ETA, and live segments iteratively
    const CHUNK_DURATION = 30
    const SAMPLE_RATE = 16000
    const CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_DURATION
    const totalSamples = audioData.length
    const numChunks = Math.max(1, Math.ceil(totalSamples / CHUNK_SAMPLES))

    for (let i = 0; i < numChunks; i++) {
      const startSample = i * CHUNK_SAMPLES
      const endSample = Math.min(startSample + CHUNK_SAMPLES, totalSamples)
      const subChunk = audioData.subarray(startSample, endSample)

      if (subChunk.length === 0) continue

      const offsetSec = i * CHUNK_DURATION
      const chunkAudioDuration = subChunk.length / SAMPLE_RATE

      const output = await transcriber(subChunk, {
        language: language === 'auto' ? null : language,
        task: 'transcribe',
        return_timestamps: true,
      })

      const chunkText = (output?.text || '').trim()
      if (chunkText) {
        accumulatedText += (accumulatedText ? ' ' : '') + chunkText
      }

      const rawChunks = output?.chunks || []
      if (rawChunks.length > 0) {
        for (const item of rawChunks) {
          const s = Array.isArray(item.timestamp) ? item.timestamp[0] ?? 0 : 0
          const e = Array.isArray(item.timestamp) ? item.timestamp[1] ?? s + 5 : s + 5
          const segText = (item.text || '').trim()
          if (segText) {
            liveSegments.push({
              start: Math.round((offsetSec + s) * 100) / 100,
              end: Math.round((offsetSec + e) * 100) / 100,
              speaker: 'Participante 1',
              text: segText,
            })
          }
        }
      } else if (chunkText) {
        liveSegments.push({
          start: Math.round(offsetSec * 100) / 100,
          end: Math.round((offsetSec + chunkAudioDuration) * 100) / 100,
          speaker: 'Participante 1',
          text: chunkText,
        })
      }

      const currentSec = Math.min(offsetSec + chunkAudioDuration, duration > 0 ? duration : offsetSec + chunkAudioDuration)
      const pct = duration > 0
        ? Math.min(90, 20 + Math.round((currentSec / duration) * 70))
        : Math.min(90, 20 + Math.round(((i + 1) / numChunks) * 70))
      const calculatedEta = duration > 0 ? etaTracker.update(currentSec, duration) : null

      self.postMessage({
        type: 'progress',
        payload: {
          id,
          progress: pct,
          stage: 'transcribing',
          message: duration > 0
            ? `Transcribiendo (${formatAudioTime(currentSec)} / ${formatAudioTime(duration)})`
            : `Transcribiendo audio (${pct}%)...`,
          eta: calculatedEta ?? undefined,
          live_text: accumulatedText.trim(),
          live_segments: liveSegments,
          model_info: `Whisper Web (${device})`,
        },
      })

      // Yield briefly to event loop to preserve worker responsiveness
      await new Promise((resolve) => setTimeout(resolve, 0))
    }

    self.postMessage({
      type: 'complete',
      payload: {
        id,
        text: accumulatedText.trim(),
        segments: liveSegments,
        duration: duration || (liveSegments[liveSegments.length - 1]?.end ?? 0),
        language,
        model_info: `Whisper Web (${device})`,
      },
    })
  } catch (error: unknown) {
    const errorMsg = error instanceof Error ? error.message : 'Error durante la transcripción en el navegador.'
    self.postMessage({
      type: 'error',
      payload: {
        id,
        error: errorMsg,
      },
    })
  }
}

