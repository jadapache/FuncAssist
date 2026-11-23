/**
 * Angular port of React `hooks/useTranscription.ts`, which only re-exported the context hook.
 * `inject(TranscriptionService)` returns the same root `TranscriptionStore` instance
 * (React: `useTranscription()` → `TranscriptionContext` value).
 */
export {
  TranscriptionStore,
  TranscriptionStore as TranscriptionService,
  type TranscriptionContextValue,
} from '../context/transcription.store'
