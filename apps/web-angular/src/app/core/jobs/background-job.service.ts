import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core'
import { api } from '../../api/client'
import { transcriptionApi } from '../../features/transcription/api/transcriptionApi'
import { ToastService } from '../notifications/toast.service'

export interface BackgroundJobItem {
  id: string
  type: 'transcription' | 'download' | 'processing'
  title: string
  progress: number
  status:
    | 'pending'
    | 'uploading'
    | 'preprocessing'
    | 'transcribing'
    | 'diarizing'
    | 'summarizing'
    | 'complete'
    | 'failed'
    | 'cancelled'
  stageText?: string
  eta?: string | null
  speedOrSize?: string | null
  onCancel?: () => void
  onClick?: () => void
  onDismiss?: () => void
}

const isTerminalStatus = (status: BackgroundJobItem['status']) =>
  status === 'complete' || status === 'failed' || status === 'cancelled'

/**
 * Angular port of React `BackgroundJobContext`.
 * Generic background job presentation coordinator for floating toasts and global counters.
 * Domain-specific stream/polling management (e.g. transcription SSE) stays in the feature stores.
 */
@Injectable({ providedIn: 'root' })
export class BackgroundJobService {
  private readonly toastService = inject(ToastService)

  private readonly jobsMap = signal<Record<string, BackgroundJobItem>>({})
  private readonly dismissTimers: Record<string, number> = {}
  private readonly dismissedJobs = new Set<string>()
  private readonly cancelledJobs = new Set<string>()

  readonly jobs = computed(() => Object.values(this.jobsMap()))
  readonly activeDownloadsCount = computed(
    () => this.jobs().filter((j) => j.type === 'download' && !isTerminalStatus(j.status)).length,
  )
  readonly activeTranscriptionsCount = computed(
    () => this.jobs().filter((j) => j.type === 'transcription' && !isTerminalStatus(j.status)).length,
  )

  constructor() {
    // Polling loop for active model downloads (500 ms, only while a download is in flight).
    const pollInterval = window.setInterval(() => void this.pollDownloads(), 500)
    inject(DestroyRef).onDestroy(() => {
      window.clearInterval(pollInterval)
      for (const timer of Object.values(this.dismissTimers)) window.clearTimeout(timer)
    })
  }

  /** Remove a job (manual dismiss or timer expiry). */
  removeJob(id: string): void {
    this.dismissedJobs.add(id)
    this.cancelledJobs.delete(id)
    if (this.dismissTimers[id]) {
      window.clearTimeout(this.dismissTimers[id])
      delete this.dismissTimers[id]
    }
    this.jobsMap.update((prev) => {
      const copy = { ...prev }
      delete copy[id]
      return copy
    })
  }

  /** Add or update any job. Terminal jobs auto-dismiss after 4 s (3 s when cancelled). */
  addOrUpdateJob(job: BackgroundJobItem): void {
    const isTerminal = isTerminalStatus(job.status)

    // If job has been cancelled, reject any incoming non-cancelled update
    if (this.cancelledJobs.has(job.id) && job.status !== 'cancelled') return
    // If user explicitly dismissed a job that is already terminal, don't resurrect it
    if (this.dismissedJobs.has(job.id) && isTerminal) return
    // If a job becomes active again, allow showing it
    if (!isTerminal && this.dismissedJobs.has(job.id)) this.dismissedJobs.delete(job.id)
    if (!isTerminal && this.cancelledJobs.has(job.id)) this.cancelledJobs.delete(job.id)

    this.jobsMap.update((prev) => ({
      ...prev,
      [job.id]: { ...(prev[job.id] || {}), ...job },
    }))

    if (isTerminal) {
      if (!this.dismissTimers[job.id]) {
        const timeoutMs = job.status === 'cancelled' ? 3000 : 4000
        this.dismissTimers[job.id] = window.setTimeout(() => {
          this.removeJob(job.id)
          delete this.dismissTimers[job.id]
        }, timeoutMs)
      }
    } else if (this.dismissTimers[job.id]) {
      // Back to in-progress: clear any pending dismissal
      window.clearTimeout(this.dismissTimers[job.id])
      delete this.dismissTimers[job.id]
    }
  }

  /** Cancel a job by ID (transcription or model download). */
  async cancelJob(id: string): Promise<void> {
    this.cancelledJobs.add(id)
    const current = this.jobsMap()[id]
    const isTranscription =
      current?.type === 'transcription' || id.startsWith('trans_') || (id.includes('-') && id.length >= 32)

    // Set cancelling state immediately for prompt visual feedback
    const cancellingText = isTranscription ? 'Cancelando transcripción...' : 'Cancelando descarga...'
    this.jobsMap.update((prev) => {
      if (!prev[id]) return prev
      return { ...prev, [id]: { ...prev[id], status: 'cancelled', stageText: cancellingText, eta: null } }
    })

    if (isTranscription) {
      try {
        await transcriptionApi.cancelTranscription(id)
        this.toastService.toast.info('Transcripción cancelada.')
      } catch (e) {
        console.warn(`Error al cancelar transcripción ${id}:`, e)
      }
    } else {
      try {
        await api.cancelBuiltinModelDownload(id)
        this.toastService.toast.info(`Descarga del modelo ${id} cancelada.`)
      } catch (e) {
        console.warn(`Error al cancelar descarga ${id}:`, e)
      }
    }

    // Mark final cancelled status in UI and reset progress
    this.addOrUpdateJob({
      id,
      type: current?.type || (isTranscription ? 'transcription' : 'download'),
      title: current?.title || (isTranscription ? 'Transcripción' : 'Descarga'),
      progress: 0,
      status: 'cancelled',
      stageText: isTranscription ? 'Transcripción cancelada' : 'Descarga cancelada',
      eta: null,
    })
  }

  /** Register a download job immediately. */
  registerDownloadJob(modelId: string, title?: string): void {
    this.dismissedJobs.delete(modelId)
    this.cancelledJobs.delete(modelId)
    if (this.dismissTimers[modelId]) {
      window.clearTimeout(this.dismissTimers[modelId])
      delete this.dismissTimers[modelId]
    }
    this.jobsMap.update((prev) => {
      const copy = { ...prev }
      delete copy[modelId]
      return {
        ...copy,
        [modelId]: {
          id: modelId,
          type: 'download',
          title: title || `Descargando modelo ${modelId}`,
          progress: 0,
          status: 'uploading',
          stageText: 'Iniciando descarga en segundo plano...',
          speedOrSize: 'Iniciando...',
          onCancel: () => void this.cancelJob(modelId),
          onDismiss: () => this.removeJob(modelId),
        },
      }
    })
  }

  private async pollDownloads(): Promise<void> {
    const hasActive = Object.values(this.jobsMap()).some((j) => j.type === 'download' && !isTerminalStatus(j.status))
    if (!hasActive) return

    try {
      const res = await api.getBuiltinDownloadTasks()
      if (!res.ok || !Array.isArray(res.tasks)) return
      for (const t of res.tasks) {
        const current = this.jobsMap()[t.id]
        const isComplete = t.status === 'complete'
        const isFailed = t.status === 'failed'
        const isCancelled = t.status === 'cancelled'

        // If locally cancelled by user, avoid reverting to uploading
        if (current?.status === 'cancelled' && t.status === 'downloading') continue

        const newStatus: BackgroundJobItem['status'] = isComplete
          ? 'complete'
          : isFailed
            ? 'failed'
            : isCancelled
              ? 'cancelled'
              : 'uploading'
        const newProgress = isComplete ? 100 : Math.max(0, t.progress)
        const newStageText = isCancelled ? 'Descarga cancelada por el usuario' : t.stageText || 'Descargando modelo...'
        const newSpeedOrSize = t.speedOrSize || current?.speedOrSize || null
        const newEta = isCancelled || isComplete ? null : t.eta

        if (
          !current ||
          current.progress !== newProgress ||
          current.status !== newStatus ||
          current.stageText !== newStageText ||
          current.speedOrSize !== newSpeedOrSize ||
          current.eta !== newEta
        ) {
          this.addOrUpdateJob({
            id: t.id,
            type: 'download',
            title: current?.title || t.title,
            progress: newProgress,
            status: newStatus,
            stageText: newStageText,
            speedOrSize: newSpeedOrSize,
            eta: newEta,
            onCancel: () => void this.cancelJob(t.id),
            onDismiss: () => this.removeJob(t.id),
          })
        }
      }
    } catch {
      // silent polling catch
    }
  }
}
