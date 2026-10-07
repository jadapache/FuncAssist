/**
 * Transcription feature — public API
 *
 * External code (App.tsx, routes, other features) should import
 * exclusively from this barrel. Internal cross-file imports inside
 * the feature use relative paths directly.
 */

// API
export { transcriptionApi } from './api/transcriptionApi'
export type {
  TranscriptionResult,
  TranscriptionSegment,
  TranscriptionSummary,
  TranscriptionProgress,
  TranscribeOptions,
  AvailableModelsInfo,
  MediaMetadata,
} from './api/transcriptionApi'

// Hooks & Context
export { useTranscription, TranscriptionProvider } from './hooks/useTranscription'
export type { TranscriptionContextValue } from './hooks/useTranscription'
export { useTranscriptionProgress } from './hooks/useTranscriptionProgress'
export type { TranscriptionProgressData } from './hooks/useTranscriptionProgress'

// Components (public-facing — used by pages or App.tsx)
export { TranscriptionStudio } from './components/TranscriptionStudio'
export { UploadArea } from './components/UploadArea'
export { ActiveTranscriptionItem } from './components/ActiveTranscriptionItem'
export { RecentTranscriptionItem } from './components/RecentTranscriptionItem'
export {
  FloatingJobToast as FloatingTranscriptionToast,
  type FloatingJobToastProps as FloatingTranscriptionToastProps,
} from '../../components/common/FloatingJobToast'
export { SummaryModal } from './components/SummaryModal'
export { GenerateModal } from './components/GenerateModal'

// Page
export { default as TranscripcionesPage } from './pages/TranscripcionesPage'
