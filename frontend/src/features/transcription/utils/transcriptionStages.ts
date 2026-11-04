export const STAGE_TRANSLATIONS: Record<string, string> = {
  pending: 'En cola...',
  uploading: 'Subiendo archivo...',
  preprocessing: 'Extrayendo audio...',
  transcribing: 'Transcribiendo...',
  diarizing: 'Identificando interlocutores...',
  summarizing: 'Generando resumen...',
  finalizing: 'Finalizando...',
  complete: 'Completado',
  failed: 'Error',
  cancelled: 'Cancelado',
}

export const getGeneralStageText = (data: {
  stage?: string
  status?: string
}): string => {
  if (data.stage === 'complete' || data.status === 'complete') return 'Completado'
  if (data.stage === 'cancelled' || data.status === 'cancelled') return 'Cancelado'
  if (data.stage === 'failed' || data.status === 'failed') return 'Error en procesamiento'

  const key = (data.stage || data.status || '').toLowerCase()
  return STAGE_TRANSLATIONS[key] || 'Transcribiendo...'
}

export const getTranscriptionStageText = (data: {
  stage?: string
  status?: string
  message?: string
  error?: string | null
}): string => {
  if (data.stage === 'complete' || data.status === 'complete') return 'Completado'
  if (data.stage === 'cancelled' || data.status === 'cancelled') return 'Transcripción cancelada'
  if (data.stage === 'failed' || data.status === 'failed') {
    return data.error || data.message || 'Error en procesamiento'
  }
  if (data.message) return data.message

  const key = (data.stage || '').toLowerCase()
  return STAGE_TRANSLATIONS[key] || 'Procesando audio...'
}

