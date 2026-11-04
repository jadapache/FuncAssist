import { useCallback, useState } from 'react'

export type TranscriptionViewMode = 'dashboard' | 'studio'

export function useTranscriptionModals() {
  const [viewMode, setViewMode] = useState<TranscriptionViewMode>('dashboard')
  const [selectedTranscriptionId, setSelectedTranscriptionId] = useState<string | null>(null)
  const [activeMeetingTitle, setActiveMeetingTitle] = useState<string>('')
  const [showProgressModal, setShowProgressModal] = useState(false)
  const [showSummaryModal, setShowSummaryModal] = useState(false)
  const [showGenerateModal, setShowGenerateModal] = useState(false)

  const openStudio = useCallback((transcriptionId: string, title?: string) => {
    setSelectedTranscriptionId(transcriptionId)
    if (title) {
      setActiveMeetingTitle(title)
    }
    setViewMode('studio')
  }, [])

  const closeStudio = useCallback(() => {
    setViewMode('dashboard')
  }, [])

  const openProgressModal = useCallback((transcriptionId: string) => {
    openStudio(transcriptionId)
  }, [openStudio])

  const openSummaryModal = useCallback((transcriptionId: string) => {
    openStudio(transcriptionId)
  }, [openStudio])

  const openGenerateModal = useCallback((transcriptionId: string, title?: string) => {
    setSelectedTranscriptionId(transcriptionId)
    if (title) {
      setActiveMeetingTitle(title)
    }
    setShowGenerateModal(true)
  }, [])

  const closeAllModals = useCallback(() => {
    setShowProgressModal(false)
    setShowSummaryModal(false)
    setShowGenerateModal(false)
  }, [])

  return {
    viewMode,
    setViewMode,
    selectedTranscriptionId,
    setSelectedTranscriptionId,
    activeMeetingTitle,
    setActiveMeetingTitle,
    showProgressModal,
    setShowProgressModal,
    showSummaryModal,
    setShowSummaryModal,
    showGenerateModal,
    setShowGenerateModal,
    openStudio,
    closeStudio,
    openProgressModal,
    openSummaryModal,
    openGenerateModal,
    closeAllModals,
  }
}

