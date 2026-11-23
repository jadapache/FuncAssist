import { useEffect } from 'react'
import { useBackgroundJobs, type BackgroundJobItem } from '../../../context/BackgroundJobContext'
import type { TranscriptionJob } from '../context/transcriptionJobs'
import { formatProgressEta } from '../utils/time'
import {
  SUMMARY_STATUS_LABELS,
  getStageText,
  isSummaryInProgress,
  isTerminalStage,
  normalizeStage,
} from '../utils/transcriptionStages'
import { useLatest } from './useLatest'

const SOURCE = 'transcription'

function toWidgetStatus(job: TranscriptionJob): BackgroundJobItem['status'] {
  switch (normalizeStage(job.stage)) {
    case 'complete':
      return 'complete'
    case 'failed':
    case 'interrupted':
      return 'failed'
    case 'cancelled':
      return 'cancelled'
    case 'uploading':
      return 'uploading'
    case 'preprocessing':
    case 'decoding':
    case 'queued':
      return 'preprocessing'
    case 'diarizing':
      return 'diarizing'
    default:
      return 'transcribing'
  }
}

function widgetText(job: TranscriptionJob): string {
  if (job.stage === 'complete' && isSummaryInProgress(job.summary_status)) {
    return `Transcripción lista · ${SUMMARY_STATUS_LABELS[job.summary_status || 'running']}…`
  }
  return getStageText(job)
}

interface AdapterActions {
  open: (job: TranscriptionJob) => void
  cancel: (id: string) => void
  dismiss: (id: string) => void
}

/**
 * Publishes a read-only projection of the transcription jobs to the floating widget. The jobs
 * reducer stays the single source of truth.
 */
export function useBackgroundJobsAdapter(jobs: TranscriptionJob[], actions: AdapterActions) {
  const { setExternalJobs } = useBackgroundJobs()
  const actionsRef = useLatest(actions)

  useEffect(() => {
    const items: BackgroundJobItem[] = jobs
      .filter((job) => !job.toastHidden)
      .map((job) => ({
        id: job.id,
        type: 'transcription',
        title: job.title,
        progress: job.progress,
        status: toWidgetStatus(job),
        stageText: widgetText(job),
        eta: isTerminalStage(job.stage) ? null : formatProgressEta(job),
        speedOrSize: null,
        onClick: () => actionsRef.current.open(job),
        onCancel: isTerminalStage(job.stage) ? undefined : () => actionsRef.current.cancel(job.id),
        onDismiss: () => actionsRef.current.dismiss(job.id),
      }))
    setExternalJobs(SOURCE, items)
  }, [jobs, setExternalJobs, actionsRef])

  useEffect(() => () => setExternalJobs(SOURCE, []), [setExternalJobs])
}
