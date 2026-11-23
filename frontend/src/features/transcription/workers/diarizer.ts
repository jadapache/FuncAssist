/// <reference lib="webworker" />
/**
 * In-browser speaker diarization for the transcription worker.
 *
 * Models (downloaded from the Hugging Face Hub once and cached by the browser, ~30 MB total):
 *  - onnx-community/pyannote-segmentation-3.0: who speaks when, inside 10 s windows.
 *  - onnx-community/wespeaker-voxceleb-resnet34-LM: one voice embedding per local speaker.
 * Embeddings are clustered across windows so the same voice keeps the same label.
 */
import { AutoModel, AutoModelForAudioFrameClassification, AutoProcessor } from '@huggingface/transformers'
import {
  MIN_EMBEDDING_SPEECH_SEC,
  assignSpeakers,
  clusterEmbeddings,
  gatherSamples,
  localSpeakers,
  planDiarizationWindows,
  poolEmbedding,
  speakerIdsByAppearance,
  type LabelledSpan,
  type LocalSpeaker,
  type PyannoteTurn,
  type TimeSpan,
} from '../utils/speakerDiarization'

const SEGMENTATION_MODEL = 'onnx-community/pyannote-segmentation-3.0'
const EMBEDDING_MODEL = 'onnx-community/wespeaker-voxceleb-resnet34-LM'

interface TensorLike {
  data: ArrayLike<number>
  dims: number[]
}

type Callable = (input: unknown) => Promise<Record<string, unknown>>

interface SegmentationProcessor {
  (audio: Float32Array): Promise<Record<string, unknown>>
  post_process_speaker_diarization: (logits: unknown, numSamples: number) => PyannoteTurn[][]
}

interface Models {
  segProcessor: SegmentationProcessor
  segModel: Callable
  embProcessor: (audio: Float32Array) => Promise<Record<string, unknown>>
  embModel: Callable
}

let cached: Promise<Models> | null = null

/** Loads (once) both models on WASM in fp32; they are small enough not to need quantisation. */
function loadModels(onDownload: (fraction: number) => void): Promise<Models> {
  if (cached) return cached
  const files = new Map<string, { loaded: number; total: number }>()
  const progressCallback = (info: { status?: string; file?: string; loaded?: number; total?: number }) => {
    if (info.status !== 'progress' || typeof info.loaded !== 'number' || !info.total) return
    files.set(info.file || 'model', { loaded: info.loaded, total: info.total })
    let loaded = 0
    let total = 0
    for (const item of files.values()) {
      loaded += item.loaded
      total += item.total
    }
    if (total > 0) onDownload(Math.min(1, loaded / total))
  }
  const modelOptions = {
    device: 'wasm',
    dtype: 'fp32',
    progress_callback: progressCallback,
  } as unknown as Parameters<typeof AutoModel.from_pretrained>[1]
  const processorOptions = { progress_callback: progressCallback } as unknown as Parameters<
    typeof AutoProcessor.from_pretrained
  >[1]

  cached = Promise.all([
    AutoProcessor.from_pretrained(SEGMENTATION_MODEL, processorOptions),
    AutoModelForAudioFrameClassification.from_pretrained(SEGMENTATION_MODEL, modelOptions),
    AutoProcessor.from_pretrained(EMBEDDING_MODEL, processorOptions),
    AutoModel.from_pretrained(EMBEDDING_MODEL, modelOptions),
  ]).then(([segProcessor, segModel, embProcessor, embModel]) => ({
    segProcessor: segProcessor as unknown as SegmentationProcessor,
    segModel: segModel as unknown as Callable,
    embProcessor: embProcessor as unknown as Models['embProcessor'],
    embModel: embModel as unknown as Callable,
  }))
  cached.catch(() => {
    cached = null // allow a later job to retry the download
  })
  return cached
}

function firstTensor(output: Record<string, unknown>): TensorLike | null {
  const preferred = output.embeddings ?? output.pooler_output ?? output.last_hidden_state
  const candidates = preferred ? [preferred] : Object.values(output)
  for (const value of candidates) {
    const tensor = value as Partial<TensorLike> | null
    if (tensor && tensor.data && Array.isArray(tensor.dims)) return tensor as TensorLike
  }
  return null
}

export interface DiarizeOptions {
  audio: Float32Array
  sampleRate: number
  /** Whisper segments in the same timeline as `audio`. */
  segments: TimeSpan[]
  numSpeakers?: number | null
  isCancelled: () => boolean
  onProgress: (fraction: number, message: string) => void
}

export interface DiarizeResult {
  /** Speaker id per segment (S1, S2…), same order as `segments`. */
  speakerIds: string[]
  speakers: number
}

export class DiarizationCancelled extends Error {}

/** Labels each segment with a speaker. Throws on model failure; the caller keeps one speaker. */
export async function diarizeSegments(options: DiarizeOptions): Promise<DiarizeResult> {
  const { audio, sampleRate, segments, numSpeakers, isCancelled, onProgress } = options
  onProgress(0, 'Preparando la identificación de interlocutores…')
  const models = await loadModels((fraction) =>
    onProgress(fraction * 0.2, `Descargando el modelo de interlocutores (${Math.round(fraction * 100)} %)…`),
  )

  const totalSec = audio.length / sampleRate
  const windows = planDiarizationWindows(totalSec)
  const speakers: LocalSpeaker[] = []
  const embeddings: Float32Array[] = []

  for (let index = 0; index < windows.length; index++) {
    if (isCancelled()) throw new DiarizationCancelled()
    const win = windows[index]
    const slice = audio.subarray(Math.round(win.start * sampleRate), Math.round(win.end * sampleRate))
    if (slice.length < sampleRate) continue // under 1 s: nothing to learn from

    const inputs = await models.segProcessor(slice)
    const { logits } = await models.segModel(inputs)
    const [turns = []] = models.segProcessor.post_process_speaker_diarization(logits, slice.length)

    for (const speaker of localSpeakers(turns, index, win.start)) {
      if (speaker.speechSec < MIN_EMBEDDING_SPEECH_SEC) continue
      const samples = gatherSamples(audio, sampleRate, speaker.spans)
      const features = await models.embProcessor(samples)
      const tensor = firstTensor(await models.embModel(features))
      if (!tensor) throw new Error('El modelo de interlocutores no devolvió un vector de voz.')
      speakers.push(speaker)
      embeddings.push(poolEmbedding(tensor.data, tensor.dims))
    }

    onProgress(
      0.2 + 0.75 * ((index + 1) / windows.length),
      `Identificando interlocutores (${index + 1} de ${windows.length})…`,
    )
    // Let a pending cancel message through between windows.
    await new Promise((resolve) => setTimeout(resolve, 0))
  }

  if (embeddings.length === 0) {
    return { speakerIds: segments.map(() => 'S1'), speakers: 1 }
  }

  const labels = clusterEmbeddings(embeddings, { numSpeakers })
  const turns: LabelledSpan[] = []
  speakers.forEach((speaker, i) => {
    for (const span of speaker.spans) turns.push({ ...span, label: labels[i] })
  })
  const speakerIds = speakerIdsByAppearance(assignSpeakers(segments, turns))
  onProgress(1, 'Interlocutores identificados.')
  return { speakerIds, speakers: new Set(speakerIds).size }
}
