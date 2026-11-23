import { useContext } from 'react'
import { TranscriptionContext, type TranscriptionContextValue } from '../context/transcriptionContextValue'

export { TranscriptionProvider } from '../context/TranscriptionContext'
export type { TranscriptionContextValue } from '../context/transcriptionContextValue'

export function useTranscription(): TranscriptionContextValue {
  const context = useContext(TranscriptionContext)
  if (!context) {
    throw new Error('useTranscription must be used within a TranscriptionProvider')
  }
  return context
}
