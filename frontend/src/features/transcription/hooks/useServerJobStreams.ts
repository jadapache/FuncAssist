import { useEffect, useMemo, useRef, type Dispatch } from 'react'
import { openProgressStream, type ProgressStreamHandle } from '../api/progressStream'
import type { JobsAction, TranscriptionJob } from '../context/transcriptionJobs'
import { isStreamFinished } from '../utils/transcriptionStages'
import { useLatest } from './useLatest'

interface ServerJobStreamsOptions {
  jobs: TranscriptionJob[]
  dispatch: Dispatch<JobsAction>
  enabled: boolean
  /** The job no longer exists on the server (deleted, or owned by someone else). */
  onNotFound: (id: string) => void
  onFatal: (id: string, message: string) => void
}

/**
 * One progress stream per running server job. Jobs still uploading are not followed yet (the
 * server job does not exist until the upload finishes); finished jobs are closed.
 */
export function useServerJobStreams({ jobs, dispatch, enabled, onNotFound, onFatal }: ServerJobStreamsOptions) {
  const streamsRef = useRef(new Map<string, ProgressStreamHandle>())
  const callbacksRef = useLatest({ onNotFound, onFatal })

  const followKey = useMemo(
    () =>
      jobs
        .filter((job) => job.kind === 'server' && job.stage !== 'uploading' && !isStreamFinished(job))
        .map((job) => job.id)
        .sort()
        .join(','),
    [jobs],
  )

  useEffect(() => {
    const streams = streamsRef.current
    const wanted = new Set(enabled && followKey ? followKey.split(',') : [])

    for (const [id, handle] of streams) {
      if (!wanted.has(id) || handle.isClosed()) {
        handle.close()
        streams.delete(id)
      }
    }
    for (const id of wanted) {
      if (streams.has(id)) continue
      streams.set(
        id,
        openProgressStream(id, {
          onProgress: (progress) => dispatch({ type: 'server_progress', progress }),
          onNotFound: () => callbacksRef.current.onNotFound(id),
          onFatal: (message) => callbacksRef.current.onFatal(id, message),
        }),
      )
    }
  }, [followKey, enabled, dispatch, callbacksRef])

  useEffect(() => {
    const streams = streamsRef.current
    return () => {
      for (const handle of streams.values()) handle.close()
      streams.clear()
    }
  }, [])
}
