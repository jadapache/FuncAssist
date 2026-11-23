import { DestroyRef, Injectable, Injector, computed, effect, inject, untracked, type Signal } from '@angular/core'
import { Router } from '@angular/router'
import type { BackgroundJobItem } from '../../../core/jobs/background-job.service'
import { transcriptionApi, type TranscriptionProgress } from '../api/transcriptionApi'
import { getGeneralStageText, getTranscriptionStageText } from '../utils/transcriptionStages'
import type { RefObject, SetStateAction } from '../utils/reactCompat'

function isNotFoundError(err: unknown): boolean {
  if (!err) return false
  const status = (err as { status?: number })?.status
  if (status === 404) return true
  const msg = err instanceof Error ? err.message : String(err)
  return msg.includes('404') || msg.toLowerCase().includes('no encontrado') || msg.toLowerCase().includes('not found')
}

export interface StreamManagerProps {
  isAuthenticated: Signal<boolean>
  isAuthLoading: Signal<boolean>
  activeJobs: Signal<Record<string, TranscriptionProgress>>
  setActiveJobs: (action: SetStateAction<Record<string, TranscriptionProgress>>) => void
  addOrUpdateJob: (job: BackgroundJobItem) => void
  removeJob: (id: string) => void
  cancelJob: (id: string) => Promise<void>
  openStudio: (id: string) => void
  refreshTranscriptions: () => Promise<void>
}

/** Same filter React used for both `activeIdsKey` and the polling loop (server-side, non-terminal jobs). */
function isServerTrackedActiveJob(
  id: string,
  job: TranscriptionProgress | undefined,
  clientJobIds: Set<string>,
): boolean {
  if (id.startsWith('upload_') || clientJobIds.has(id)) return false
  if (job?.model_info === 'Whisper Web (Client)') return false
  const inactive = ['complete', 'failed', 'cancelled', 'uploading']
  return !inactive.includes(job?.status as string)
}

/**
 * Angular port of React `useTranscriptionStreamManager`.
 *
 * Global (root) service: React only used this hook inside `TranscriptionProvider`. The hook props
 * arrive through {@link configure}, called once by `TranscriptionStore`. It keeps one EventSource
 * per server-side job plus a 2.5 s polling fallback, exactly like the React hook.
 */
@Injectable({ providedIn: 'root' })
export class TranscriptionStreamManagerService {
  private readonly router = inject(Router)
  private readonly injector = inject(Injector)

  private props: StreamManagerProps | null = null

  private pollingTimer: number | null = null
  private eventSources: Record<string, EventSource> = {}

  readonly abortControllersRef: RefObject<Record<string, AbortController>> = { current: {} }
  readonly cancelledJobsRef: RefObject<Set<string>> = { current: new Set() }
  readonly activeWorkersRef: RefObject<Record<string, Worker>> = { current: {} }
  readonly clientJobIdsRef: RefObject<Set<string>> = { current: new Set() }

  private readonly activeIdsKey = computed(() => {
    const activeJobs = this.props?.activeJobs() ?? {}
    return Object.keys(activeJobs)
      .filter((id) => isServerTrackedActiveJob(id, activeJobs[id], this.clientJobIdsRef.current))
      .sort()
      .join(',')
  })

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.pollingTimer) {
        clearInterval(this.pollingTimer)
        this.pollingTimer = null
      }
      for (const ctrl of Object.values(this.abortControllersRef.current)) {
        ctrl.abort()
      }
      this.abortControllersRef.current = {}
      for (const es of Object.values(this.eventSources)) {
        es?.close()
      }
      this.eventSources = {}
    })
  }

  /** Receives the React hook props. Must be called once (by `TranscriptionStore`). */
  configure(props: StreamManagerProps): void {
    if (this.props) return
    this.props = props

    // React: useEffect(..., [activeIdsKey, isAuthenticated, isAuthLoading, ...])
    effect(
      () => {
        const key = this.activeIdsKey()
        const isAuthenticated = props.isAuthenticated()
        const isAuthLoading = props.isAuthLoading()
        untracked(() => this.syncStreams(key, isAuthenticated, isAuthLoading))
      },
      { injector: this.injector },
    )
  }

  handleDismissJob(id: string): void {
    this.clientJobIdsRef.current.delete(id)
    this.cancelledJobsRef.current.delete(id)
    if (this.abortControllersRef.current[id]) {
      this.abortControllersRef.current[id].abort()
      delete this.abortControllersRef.current[id]
    }
    if (this.eventSources[id]) {
      this.eventSources[id].close()
      delete this.eventSources[id]
    }
    this.props?.setActiveJobs((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    this.props?.removeJob(id)
  }

  async handleCancelTranscription(transcriptionId: string): Promise<void> {
    const props = this.props
    if (!props) return
    try {
      this.cancelledJobsRef.current.add(transcriptionId)

      if (this.abortControllersRef.current[transcriptionId]) {
        this.abortControllersRef.current[transcriptionId].abort()
        delete this.abortControllersRef.current[transcriptionId]
      }
      if (this.eventSources[transcriptionId]) {
        this.eventSources[transcriptionId].close()
        delete this.eventSources[transcriptionId]
      }
      if (this.activeWorkersRef.current[transcriptionId]) {
        this.activeWorkersRef.current[transcriptionId].terminate()
        delete this.activeWorkersRef.current[transcriptionId]
      }

      props.setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[transcriptionId]
        return next
      })

      await props.cancelJob(transcriptionId)
      await props.refreshTranscriptions()
    } catch (err) {
      console.warn('Error cancelling transcription:', err)
    }
  }

  private syncJobUi(
    id: string,
    title: string,
    progress: number,
    status: string,
    stageText: string,
    eta?: string | null,
  ): void {
    const props = this.props
    if (!props) return
    props.addOrUpdateJob({
      id,
      type: 'transcription',
      title,
      progress,
      status: status as BackgroundJobItem['status'],
      stageText,
      speedOrSize: null,
      eta: eta || null,
      onClick: () => {
        props.openStudio(id)
        void this.router.navigateByUrl('/transcripciones')
      },
      onCancel: () => void this.handleCancelTranscription(id),
      onDismiss: () => this.handleDismissJob(id),
    })
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async processJobPayload(id: string, data: any): Promise<void> {
    const props = this.props
    if (!props) return
    if (this.cancelledJobsRef.current.has(id)) return

    if (typeof data.message === 'string' && data.message.toLowerCase().includes('no encontrado')) {
      this.handleDismissJob(id)
      return
    }

    const isCancelled = data.stage === 'cancelled' || data.status === 'cancelled'
    if (isCancelled) {
      this.cancelledJobsRef.current.add(id)
      this.eventSources[id]?.close()
      delete this.eventSources[id]
      props.setActiveJobs((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
      this.syncJobUi(id, data.title || 'Transcripción', 0, 'cancelled', 'Transcripción cancelada')
      return
    }

    const updatedProgress = typeof data.progress === 'number' ? data.progress : 0
    const isDone = data.stage === 'complete' || updatedProgress === 100
    const isFail = data.stage === 'failed'
    const updatedStatus: TranscriptionProgress['status'] = isDone ? 'complete' : isFail ? 'failed' : 'transcribing'
    const stageText = getTranscriptionStageText(data)
    const generalStageText = getGeneralStageText(data)

    // React read `activeJobsRef.current` (last committed state) for the toast title.
    const previousTitle = props.activeJobs()[id]?.title

    props.setActiveJobs((prev) => {
      if (this.cancelledJobsRef.current.has(id)) return prev
      const existing = prev[id]
      const finalProgress = typeof data.progress === 'number' ? data.progress : existing?.progress || 0
      return {
        ...prev,
        [id]: {
          id,
          media_id: existing?.media_id || data.media_id || '',
          title: data.title || existing?.title,
          status: updatedStatus,
          stage: data.stage || existing?.stage,
          progress: isDone ? 100 : finalProgress,
          message: data.message || stageText,
          preview: data.preview,
          eta: isDone || isFail ? null : data.eta || existing?.eta,
          model_info: data.model_info || existing?.model_info,
          error: data.error,
          live_segments: data.live_segments || existing?.live_segments || [],
          live_text: data.live_text || existing?.live_text || '',
        },
      }
    })

    this.syncJobUi(
      id,
      data.title || previousTitle || 'Transcripción',
      isDone ? 100 : updatedProgress,
      updatedStatus,
      generalStageText,
      isDone || isFail ? null : data.eta,
    )

    if (isDone || isFail) {
      this.eventSources[id]?.close()
      delete this.eventSources[id]
      if (isDone) await props.refreshTranscriptions()
    }
  }

  /** Body of the React SSE/polling effect. */
  private syncStreams(activeIdsKey: string, isAuthenticated: boolean, isAuthLoading: boolean): void {
    const props = this.props
    if (!props) return
    if (!isAuthenticated || isAuthLoading) return
    const activeIds = activeIdsKey ? activeIdsKey.split(',') : []

    for (const id of activeIds) {
      if (this.clientJobIdsRef.current.has(id) || this.eventSources[id]) continue
      try {
        const es = new EventSource(transcriptionApi.getProgressStreamUrl(id))
        this.eventSources[id] = es

        es.addEventListener('message', (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.stage === 'heartbeat' || data.event === 'heartbeat' || data.event === 'connected') return
            void this.processJobPayload(id, data)
          } catch (err) {
            console.warn('Error parsing SSE in TranscriptionContext:', err)
          }
        })

        es.onerror = () => {
          if (es.readyState === EventSource.CLOSED) {
            es.close()
            delete this.eventSources[id]
          }
        }
      } catch (err) {
        console.warn('Could not start EventSource for job:', id, err)
      }
    }

    for (const id of Object.keys(this.eventSources)) {
      if (!activeIds.includes(id)) {
        this.eventSources[id]?.close()
        delete this.eventSources[id]
      }
    }

    if (activeIds.length > 0 && !this.pollingTimer) {
      this.pollingTimer = window.setInterval(async () => {
        const activeJobs = props.activeJobs()
        const currentActive = Object.keys(activeJobs).filter((id) =>
          isServerTrackedActiveJob(id, activeJobs[id], this.clientJobIdsRef.current),
        )

        if (currentActive.length === 0) {
          if (this.pollingTimer) {
            clearInterval(this.pollingTimer)
            this.pollingTimer = null
          }
          return
        }

        for (const id of currentActive) {
          if (this.cancelledJobsRef.current.has(id)) continue
          try {
            const status = await transcriptionApi.getTranscriptionStatus(id)
            if (!status) continue
            await this.processJobPayload(id, status)
          } catch (err: unknown) {
            if (isNotFoundError(err)) {
              this.handleDismissJob(id)
            }
          }
        }
      }, 2500)
    } else if (activeIds.length === 0 && this.pollingTimer) {
      clearInterval(this.pollingTimer)
      this.pollingTimer = null
    }
  }
}
