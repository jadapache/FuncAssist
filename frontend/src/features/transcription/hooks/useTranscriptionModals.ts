import { useCallback, useState } from 'react'

export type TranscriptionViewMode = 'dashboard' | 'studio'

/** Which transcription is open and whether the deliverables modal is shown. */
export function useTranscriptionModals() {
  const [viewMode, setViewMode] = useState<TranscriptionViewMode>('dashboard')
  const [selectedTranscriptionId, setSelectedTranscriptionId] = useState<string | null>(null)
  const [activeMeetingTitle, setActiveMeetingTitle] = useState<string>('')
  const [showGenerateModal, setShowGenerateModal] = useState(false)

  const openStudio = useCallback((transcriptionId: string, title?: string) => {
    setSelectedTranscriptionId(transcriptionId)
    if (title) setActiveMeetingTitle(title)
    setViewMode('studio')
  }, [])

  const closeStudio = useCallback(() => {
    setViewMode('dashboard')
  }, [])

  return {
    viewMode,
    setViewMode,
    selectedTranscriptionId,
    setSelectedTranscriptionId,
    activeMeetingTitle,
    showGenerateModal,
    setShowGenerateModal,
    openStudio,
    closeStudio,
  }
}
