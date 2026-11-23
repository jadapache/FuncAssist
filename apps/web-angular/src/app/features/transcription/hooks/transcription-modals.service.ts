import { Injectable, signal } from '@angular/core'
import { resolveStateAction, type SetStateAction } from '../utils/reactCompat'

export type TranscriptionViewMode = 'dashboard' | 'studio'

/**
 * Angular port of React `useTranscriptionModals`.
 * React only called this hook inside the global `TranscriptionProvider`, so its state is global
 * (root service consumed by `TranscriptionStore`).
 */
@Injectable({ providedIn: 'root' })
export class TranscriptionModalsService {
  private readonly _viewMode = signal<TranscriptionViewMode>('dashboard')
  private readonly _selectedTranscriptionId = signal<string | null>(null)
  private readonly _activeMeetingTitle = signal<string>('')
  private readonly _showProgressModal = signal(false)
  private readonly _showSummaryModal = signal(false)
  private readonly _showGenerateModal = signal(false)

  readonly viewMode = this._viewMode.asReadonly()
  readonly selectedTranscriptionId = this._selectedTranscriptionId.asReadonly()
  readonly activeMeetingTitle = this._activeMeetingTitle.asReadonly()
  readonly showProgressModal = this._showProgressModal.asReadonly()
  readonly showSummaryModal = this._showSummaryModal.asReadonly()
  readonly showGenerateModal = this._showGenerateModal.asReadonly()

  setViewMode(action: SetStateAction<TranscriptionViewMode>): void {
    this._viewMode.update((prev) => resolveStateAction(action, prev))
  }

  setSelectedTranscriptionId(action: SetStateAction<string | null>): void {
    this._selectedTranscriptionId.update((prev) => resolveStateAction(action, prev))
  }

  setActiveMeetingTitle(action: SetStateAction<string>): void {
    this._activeMeetingTitle.update((prev) => resolveStateAction(action, prev))
  }

  setShowProgressModal(action: SetStateAction<boolean>): void {
    this._showProgressModal.update((prev) => resolveStateAction(action, prev))
  }

  setShowSummaryModal(action: SetStateAction<boolean>): void {
    this._showSummaryModal.update((prev) => resolveStateAction(action, prev))
  }

  setShowGenerateModal(action: SetStateAction<boolean>): void {
    this._showGenerateModal.update((prev) => resolveStateAction(action, prev))
  }

  openStudio(transcriptionId: string, title?: string): void {
    this._selectedTranscriptionId.set(transcriptionId)
    if (title) {
      this._activeMeetingTitle.set(title)
    }
    this._viewMode.set('studio')
  }

  closeStudio(): void {
    this._viewMode.set('dashboard')
  }

  openProgressModal(transcriptionId: string): void {
    this.openStudio(transcriptionId)
  }

  openSummaryModal(transcriptionId: string): void {
    this.openStudio(transcriptionId)
  }

  openGenerateModal(transcriptionId: string, title?: string): void {
    this._selectedTranscriptionId.set(transcriptionId)
    if (title) {
      this._activeMeetingTitle.set(title)
    }
    this._showGenerateModal.set(true)
  }

  closeAllModals(): void {
    this._showProgressModal.set(false)
    this._showSummaryModal.set(false)
    this._showGenerateModal.set(false)
  }
}
