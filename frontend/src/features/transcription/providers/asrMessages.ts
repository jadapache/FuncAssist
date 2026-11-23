/** Messages exchanged between BrowserAsrProvider and transcription.worker.ts. */

export interface AsrSegment {
  start: number
  end: number
  text: string
  /** Speaker id (S1, S2…) when in-browser diarization ran. */
  speakerId?: string
}

export interface AsrRequest {
  id: string
  /** 16 kHz mono samples. Transferred to the worker: the caller must not reuse the array. */
  audio: Float32Array
  language: string
  modelId: string
  duration: number
  /** Identify speakers in the worker (pyannote segmentation + WeSpeaker embeddings). */
  diarize?: boolean
  /** Exact number of speakers when known; otherwise estimated. */
  numSpeakers?: number | null
}

export interface AsrProgress {
  id: string
  stage: 'model_download' | 'transcribing' | 'diarizing'
  /** 0..1 within the stage. */
  stageProgress: number
  message: string
  etaSeconds?: number | null
  modelInfo?: string
}

export interface AsrResult {
  id: string
  text: string
  segments: AsrSegment[]
  duration: number
  language: string
  modelInfo: string
  /** Seconds of silence skipped by the voice activity detector. */
  silenceTrimmedSec: number
  /** "browser" when segments carry speaker ids from the worker's diarization. */
  diarization: 'browser' | 'none'
  /** Why diarization was requested but not applied (model load failure, no speech…). */
  diarizationWarning?: string
}

export type WorkerInMessage =
  | { type: 'transcribe'; payload: AsrRequest }
  | { type: 'cancel'; id: string }

export type WorkerOutMessage =
  | { type: 'progress'; payload: AsrProgress }
  | { type: 'segments'; payload: { id: string; segments: AsrSegment[] } }
  | { type: 'complete'; payload: AsrResult }
  | { type: 'error'; payload: { id: string; error: string } }
  | { type: 'cancelled'; payload: { id: string } }
