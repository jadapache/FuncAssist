import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core'
import { Router } from '@angular/router'
import { AuthService } from '../../../core/auth/auth.service'
import { BackgroundJobService } from '../../../core/jobs/background-job.service'
import { ToastService } from '../../../core/notifications/toast.service'
import {
  transcriptionApi,
  type AvailableModelsInfo,
  type TranscriptionProgress,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { TranscriptionModalsService, type TranscriptionViewMode } from '../hooks/transcription-modals.service'
import { TranscriptionPipelineService } from '../hooks/transcription-pipeline.service'
import { TranscriptionStreamManagerService } from '../hooks/transcription-stream-manager.service'
import { resolveStateAction, type SetStateAction } from '../utils/reactCompat'
import { STAGE_TRANSLATIONS, getGeneralStageText, getTranscriptionStageText } from '../utils/transcriptionStages'
import { loadStoredActiveJobs, saveActiveJobsToStorage } from '../utils/transcriptionStorage'

export { STAGE_TRANSLATIONS, getGeneralStageText, getTranscriptionStageText }

/**
 * Angular port of React `TranscriptionContext` / `TranscriptionProvider` (global job tracking).
 *
 * Injected eagerly by `App` (React mounted the provider at boot). At startup it:
 * - wires the stream manager (one EventSource per server job + 2.5 s polling fallback) and the
 *   upload/transcription pipeline;
 * - once the session is validated: loads the configured ASR models, the transcription list and
 *   resumes the active jobs persisted in localStorage (`qa_active_transcription_jobs`), publishing
 *   each one to `BackgroundJobService` so the floating toast shows them;
 * - persists every change of the active jobs back to localStorage.
 */
@Injectable({ providedIn: 'root' })
export class TranscriptionStore {
  private readonly toastService = inject(ToastService)
  private readonly router = inject(Router)
  private readonly backgroundJobs = inject(BackgroundJobService)
  private readonly auth = inject(AuthService)
  private readonly modals = inject(TranscriptionModalsService)
  private readonly streamManager = inject(TranscriptionStreamManagerService)
  private readonly pipeline = inject(TranscriptionPipelineService)

  private readonly activeJobsMap = signal<Record<string, TranscriptionProgress>>({})
  private readonly _recentTranscriptions = signal<TranscriptionResult[]>([])
  private readonly _availableModels = signal<AvailableModelsInfo | null>(null)
  private readonly _isLoadingList = signal(false)
  private readonly _isUploading = signal(false)

  /**
   * React wrote the (still empty) initial state to localStorage before the session was validated,
   * wiping the persisted jobs before they could be restored. Persisting only after the first restore
   * keeps the documented "resume active jobs" behaviour working.
   */
  private persistenceReady = false

  // ---- Context value (same names as React `TranscriptionContextValue`) ----
  readonly viewMode = this.modals.viewMode
  readonly activeJobs = computed(() => Object.values(this.activeJobsMap()))
  readonly recentTranscriptions = this._recentTranscriptions.asReadonly()
  readonly availableModels = this._availableModels.asReadonly()
  readonly isLoadingList = this._isLoadingList.asReadonly()
  readonly isUploading = this._isUploading.asReadonly()
  readonly showProgressModal = this.modals.showProgressModal
  readonly showSummaryModal = this.modals.showSummaryModal
  readonly showGenerateModal = this.modals.showGenerateModal
  readonly selectedTranscriptionId = this.modals.selectedTranscriptionId
  readonly activeMeetingTitle = this.modals.activeMeetingTitle
  readonly currentProgress = computed<TranscriptionProgress | null>(() => {
    const selectedId = this.modals.selectedTranscriptionId()
    return selectedId ? this.activeJobsMap()[selectedId] || null : null
  })

  constructor() {
    const setActiveJobs = (action: SetStateAction<Record<string, TranscriptionProgress>>) =>
      this.activeJobsMap.update((prev) => resolveStateAction(action, prev))

    this.streamManager.configure({
      isAuthenticated: this.auth.isAuthenticated,
      isAuthLoading: this.auth.isLoading,
      activeJobs: this.activeJobsMap,
      setActiveJobs,
      addOrUpdateJob: (job) => this.backgroundJobs.addOrUpdateJob(job),
      removeJob: (id) => this.backgroundJobs.removeJob(id),
      cancelJob: (id) => this.backgroundJobs.cancelJob(id),
      openStudio: (id) => this.modals.openStudio(id),
      refreshTranscriptions: () => this.refreshTranscriptions(),
    })

    this.pipeline.configure({
      availableModels: this._availableModels,
      activeJobs: this.activeJobsMap,
      setActiveJobs,
      recentTranscriptions: this._recentTranscriptions,
      setRecentTranscriptions: (action) => this._recentTranscriptions.update((prev) => resolveStateAction(action, prev)),
      setIsUploading: (val) => this._isUploading.set(val),
      openStudio: (id, title) => this.modals.openStudio(id, title),
      setActiveMeetingTitle: (title) => this.modals.setActiveMeetingTitle(title),
      setSelectedTranscriptionId: (id) => this.modals.setSelectedTranscriptionId(id),
      selectedTranscriptionId: this.modals.selectedTranscriptionId,
      activeMeetingTitle: this.modals.activeMeetingTitle,
      setViewMode: (action) => this.modals.setViewMode(action),
      addOrUpdateJob: (job) => this.backgroundJobs.addOrUpdateJob(job),
      removeJob: (id) => this.backgroundJobs.removeJob(id),
      handleCancelTranscription: (id) => this.streamManager.handleCancelTranscription(id),
      handleDismissJob: (id) => this.streamManager.handleDismissJob(id),
      toast: this.toastService.toast,
      abortControllersRef: this.streamManager.abortControllersRef,
      cancelledJobsRef: this.streamManager.cancelledJobsRef,
      activeWorkersRef: this.streamManager.activeWorkersRef,
      clientJobIdsRef: this.streamManager.clientJobIdsRef,
    })

    // Fetch available models and restore persisted jobs on mount / auth change
    effect(() => {
      const isAuthenticated = this.auth.isAuthenticated()
      const isAuthLoading = this.auth.isLoading()
      untracked(() => {
        if (!isAuthenticated || isAuthLoading) {
          this._recentTranscriptions.set([])
          this._availableModels.set(null)
          return
        }

        transcriptionApi
          .getAvailableModels()
          .then((models) => this._availableModels.set(models))
          .catch((e) => console.warn('Could not load models info:', e))

        void this.refreshTranscriptions()
        this.restorePersistedJobs()
        this.persistenceReady = true
        saveActiveJobsToStorage(this.activeJobsMap(), this.streamManager.clientJobIdsRef.current)
      })
    })

    // Save active jobs changes to localStorage
    effect(() => {
      const jobs = this.activeJobsMap()
      untracked(() => {
        if (!this.persistenceReady) return
        saveActiveJobsToStorage(jobs, this.streamManager.clientJobIdsRef.current)
      })
    })
  }

  // ---- Actions (same names as React) ----

  setViewMode(action: SetStateAction<TranscriptionViewMode>): void {
    this.modals.setViewMode(action)
  }

  openStudio(transcriptionId: string, title?: string): void {
    this.modals.openStudio(transcriptionId, title)
  }

  closeStudio(): void {
    this.modals.closeStudio()
  }

  async refreshTranscriptions(): Promise<void> {
    if (!this.auth.isAuthenticated()) return
    try {
      this._isLoadingList.set(true)
      const res = await transcriptionApi.listTranscriptions()
      this._recentTranscriptions.set(res.transcriptions || [])
    } catch (err) {
      console.warn('Error fetching transcriptions list:', err)
    } finally {
      this._isLoadingList.set(false)
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handleUploadAndStart(file: any, title: string, description?: string): Promise<void> {
    return this.pipeline.handleUploadAndStart(file, title, description)
  }

  handleRetranscribe(transcriptionId: string, title?: string): Promise<void> {
    return this.pipeline.handleRetranscribe(transcriptionId, title)
  }

  handleCancelTranscription(transcriptionId: string): Promise<void> {
    return this.streamManager.handleCancelTranscription(transcriptionId)
  }

  handleDeleteTranscription(transcriptionId: string): Promise<void> {
    return this.pipeline.handleDeleteTranscription(transcriptionId)
  }

  handleDismissJob(id: string): void {
    this.streamManager.handleDismissJob(id)
  }

  openProgressModal(transcriptionId: string): void {
    this.modals.openProgressModal(transcriptionId)
  }

  openSummaryModal(transcriptionId: string): void {
    this.modals.openSummaryModal(transcriptionId)
  }

  openGenerateModal(transcriptionId: string): void {
    this.modals.openGenerateModal(transcriptionId)
  }

  closeAllModals(): void {
    this.modals.closeAllModals()
  }

  setShowProgressModal(action: SetStateAction<boolean>): void {
    this.modals.setShowProgressModal(action)
  }

  setShowSummaryModal(action: SetStateAction<boolean>): void {
    this.modals.setShowSummaryModal(action)
  }

  setShowGenerateModal(action: SetStateAction<boolean>): void {
    this.modals.setShowGenerateModal(action)
  }

  /** Restore stored active jobs on authentication (React `restorePersistedJobs`). */
  private restorePersistedJobs(): void {
    const validJobs = loadStoredActiveJobs()
    if (Object.keys(validJobs).length === 0) return

    this.activeJobsMap.set(validJobs)
    for (const [id, job] of Object.entries(validJobs)) {
      this.backgroundJobs.addOrUpdateJob({
        id,
        type: 'transcription',
        title: job.title || 'Transcripción',
        progress: typeof job.progress === 'number' ? job.progress : 0,
        status: job.status,
        stageText: getTranscriptionStageText(job),
        speedOrSize: job.preview || null,
        eta: job.eta || null,
        onClick: () => {
          this.modals.openStudio(id)
          void this.router.navigateByUrl('/transcripciones')
        },
        onCancel: () => void this.streamManager.handleCancelTranscription(id),
        onDismiss: () => this.streamManager.handleDismissJob(id),
      })
    }
  }
}

/** Same shape as React `TranscriptionContextValue`. */
export type TranscriptionContextValue = TranscriptionStore
