import { useEffect, useState } from 'react'
import { errorStatus, transcriptionApi, type TranscriptionResult } from '../api/transcriptionApi'
import type { TranscriptionJob } from '../context/transcriptionJobs'
import { isTerminalStage } from '../utils/transcriptionStages'

export type RecordLoadState = 'loading' | 'loaded' | 'not_found' | 'error'

/**
 * Loads the saved transcription shown in the studio. While its job runs nothing is fetched (the
 * previous version, if any, stays visible); it reloads when the job finishes and when the
 * summary status changes.
 */
export function useTranscriptionRecord(transcriptionId: string, job: TranscriptionJob | null) {
  const [record, setRecord] = useState<TranscriptionResult | null>(null)
  const [loadState, setLoadState] = useState<RecordLoadState>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const jobRunning = Boolean(job && !isTerminalStage(job.stage))
  const jobKey = job ? `${job.stage}|${job.summary_status ?? ''}` : 'none'

  // A different transcription: forget the previous one.
  useEffect(() => {
    setRecord(null)
    setLoadState('loading')
    setLoadError(null)
  }, [transcriptionId])

  useEffect(() => {
    if (jobRunning) return
    let cancelled = false
    transcriptionApi
      .getTranscriptionResult(transcriptionId)
      .then((result) => {
        if (cancelled) return
        setRecord(result)
        setLoadState('loaded')
        setLoadError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setLoadState(errorStatus(err) === 404 ? 'not_found' : 'error')
        setLoadError(err instanceof Error ? err.message : 'No se pudo cargar la transcripción.')
      })
    return () => {
      cancelled = true
    }
  }, [transcriptionId, jobRunning, jobKey, reloadToken])

  return {
    record,
    setRecord,
    loadState,
    loadError,
    reload: () => setReloadToken((token) => token + 1),
  }
}
