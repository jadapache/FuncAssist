import { createContext } from 'react'
import type { AvailableModelsInfo, TranscriptionResult } from '../api/transcriptionApi'
import type { TranscriptionViewMode } from '../hooks/useTranscriptionModals'
import type { UploadJobOptions } from '../hooks/useTranscriptionJobRunners'
import type { TranscriptionJob } from './transcriptionJobs'

export interface TranscriptionContextValue {
  viewMode: TranscriptionViewMode
  openStudio: (transcriptionId: string, title?: string) => void
  closeStudio: () => void
  /** Every job in the store, newest first (running, failed or just finished). */
  activeJobs: TranscriptionJob[]
  /** Job of the transcription open in the studio, if any. */
  currentJob: TranscriptionJob | null
  recentTranscriptions: TranscriptionResult[]
  availableModels: AvailableModelsInfo | null
  /** Groq/OpenAI configured: uploads go to the server (and support diarization options). */
  isCloudProvider: boolean
  isLoadingList: boolean
  showGenerateModal: boolean
  setShowGenerateModal: (open: boolean) => void
  selectedTranscriptionId: string | null
  activeMeetingTitle: string
  startTranscription: (file: File, title: string, description: string, options: UploadJobOptions) => Promise<void>
  regenerateTranscription: (
    record: Pick<TranscriptionResult, 'id' | 'media_id' | 'metadata'>,
    options?: UploadJobOptions,
  ) => Promise<void>
  retryTranscription: (transcriptionId: string, title?: string) => Promise<void>
  cancelTranscription: (transcriptionId: string) => Promise<void>
  dismissJob: (transcriptionId: string) => void
  deleteTranscription: (transcriptionId: string) => Promise<void>
  refreshTranscriptions: () => Promise<void>
  /** Merges an updated record (summary, speakers…) into the list. */
  upsertRecent: (record: TranscriptionResult) => void
}

export const TranscriptionContext = createContext<TranscriptionContextValue | undefined>(undefined)
