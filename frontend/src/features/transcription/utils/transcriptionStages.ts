import type {
  SummaryStatus,
  TranscriptionProgress,
  TranscriptionStage,
} from '../api/transcriptionApi'

/** Single source of the user-facing stage names (docs/TRANSCRIPTION_PROCESS.md §3). */
export const STAGE_LABELS: Record<TranscriptionStage, string> = {
  uploading: 'Subiendo archivo',
  queued: 'En cola',
  preprocessing: 'Preparando audio',
  transcribing: 'Transcribiendo',
  cleaning: 'Limpiando texto',
  diarizing: 'Identificando interlocutores',
  saving: 'Guardando',
  complete: 'Completado',
  failed: 'Error',
  cancelled: 'Cancelado',
  interrupted: 'Interrumpida',
  decoding: 'Decodificando audio',
  model_download: 'Descargando modelo',
}

export const SUMMARY_STATUS_LABELS: Record<SummaryStatus, string> = {
  pending: 'Resumen en cola',
  running: 'Generando resumen',
  done: 'Resumen listo',
  failed: 'No se pudo generar el resumen',
  skipped: 'Resumen no solicitado',
}

const TERMINAL_STAGES: ReadonlySet<string> = new Set(['complete', 'failed', 'cancelled', 'interrupted'])

/** Stages written by older backends, mapped to the current contract. */
const LEGACY_STAGES: Record<string, TranscriptionStage> = {
  pending: 'queued',
  summarizing: 'saving',
  finalizing: 'saving',
  completed: 'complete',
}

export function normalizeStage(raw?: string | null): TranscriptionStage {
  const key = (raw || '').toLowerCase()
  if (key in STAGE_LABELS) return key as TranscriptionStage
  return LEGACY_STAGES[key] || 'transcribing'
}

export function isTerminalStage(stage?: string | null): boolean {
  return TERMINAL_STAGES.has(normalizeStage(stage))
}

export function isSummaryInProgress(status?: SummaryStatus | null): boolean {
  return status === 'pending' || status === 'running'
}

/**
 * The progress stream ends after a terminal stage, except that a `complete` job stays open
 * while its summary is pending or running.
 */
export function isStreamFinished(progress: Pick<TranscriptionProgress, 'stage' | 'summary_status'>): boolean {
  const stage = normalizeStage(progress.stage)
  if (!isTerminalStage(stage)) return false
  return !(stage === 'complete' && isSummaryInProgress(progress.summary_status))
}

export type StageRanges = Partial<Record<TranscriptionStage, readonly [number, number]>>

export const SERVER_STAGE_RANGES: StageRanges = {
  uploading: [0, 10],
  queued: [10, 10],
  preprocessing: [10, 20],
  transcribing: [20, 80],
  cleaning: [80, 85],
  diarizing: [85, 95],
  saving: [95, 99],
  complete: [100, 100],
}

/** In-browser jobs: decoding and model download happen before Whisper runs. */
export const BROWSER_STAGE_RANGES: StageRanges = {
  decoding: [0, 10],
  model_download: [10, 20],
  transcribing: [20, 85],
  diarizing: [85, 95],
  saving: [95, 99],
  complete: [100, 100],
}

/** Overall 0..100 progress for a stage and a 0..1 progress inside it. */
export function overallProgress(stage: TranscriptionStage, stageProgress: number, ranges: StageRanges): number {
  const range = ranges[stage]
  if (!range) return 0
  const fraction = Number.isFinite(stageProgress) ? Math.min(1, Math.max(0, stageProgress)) : 0
  return Math.round(range[0] + (range[1] - range[0]) * fraction)
}

export function stageLabel(stage?: string | null): string {
  return STAGE_LABELS[normalizeStage(stage)]
}

/** Detailed text for the studio and the floating widget. Failures show the real error. */
export function getStageText(progress: Pick<
  TranscriptionProgress,
  'stage' | 'message' | 'error' | 'queue_position' | 'chunks_done' | 'chunks_total'
>): string {
  const stage = normalizeStage(progress.stage)
  switch (stage) {
    case 'failed':
      return progress.error || progress.message || 'Error en el procesamiento.'
    case 'cancelled':
      return 'Transcripción cancelada'
    case 'interrupted':
      return progress.error || 'El procesamiento se interrumpió (reinicio del servidor). Puedes reintentarlo.'
    case 'complete':
      return 'Completado'
    case 'queued':
      if (typeof progress.queue_position === 'number' && progress.queue_position > 0) {
        return `En cola (posición ${progress.queue_position})`
      }
      return progress.message || 'En cola…'
    case 'transcribing':
      if (progress.message) return progress.message
      if (progress.chunks_total && progress.chunks_total > 1) {
        const current = Math.min(progress.chunks_total, (progress.chunks_done || 0) + 1)
        return `Transcribiendo fragmento ${current} de ${progress.chunks_total}…`
      }
      return 'Transcribiendo…'
    default:
      return progress.message || `${STAGE_LABELS[stage]}…`
  }
}
