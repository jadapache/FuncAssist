import { useCallback, useEffect, useState } from 'react'
import { api, type AISettings } from '../../../../api/client'
import { useToast } from '../../../../context/ToastContext'

export type CleanupMode = 'off' | 'rules' | 'llm'
export type DiarizationMode = 'auto' | 'off'

export const MAX_VOCABULARY_CHARS = 1000

/** Splits the filler textarea (commas or new lines) into a clean, de-duplicated list. */
export function parseFillerList(raw: string): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const item of raw.split(/[\n,;]+/)) {
    const value = item.trim().toLowerCase()
    if (value && !seen.has(value)) {
      seen.add(value)
      result.push(value)
    }
  }
  return result
}

/** Cleanup, diarization (server and in-browser), vocabulary and filler preferences (PUT /api/ai/settings). */
export function useTranscriptionProcessingSettings(ai: AISettings | null) {
  const { toast } = useToast()
  const [vocabulary, setVocabulary] = useState('')
  const [fillers, setFillers] = useState('')
  const [cleanup, setCleanup] = useState<CleanupMode>('rules')
  const [diarization, setDiarization] = useState<DiarizationMode>('auto')
  const [browserDiarization, setBrowserDiarization] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!ai) return
    setVocabulary(ai.transcription_vocabulary || '')
    setFillers((ai.transcription_fillers || []).join(', '))
    setCleanup(ai.transcription_cleanup || 'rules')
    setDiarization(ai.transcription_diarization || 'auto')
    setBrowserDiarization(ai.transcription_browser_diarization === 'on')
  }, [ai])

  const save = useCallback(async () => {
    setSaving(true)
    try {
      const updated = await api.updateAiSettings({
        transcription_vocabulary: vocabulary.trim().slice(0, MAX_VOCABULARY_CHARS),
        transcription_fillers: parseFillerList(fillers),
        transcription_cleanup: cleanup,
        transcription_diarization: diarization,
        transcription_browser_diarization: browserDiarization ? 'on' : 'off',
      })
      setVocabulary(updated.transcription_vocabulary ?? vocabulary.trim())
      setFillers((updated.transcription_fillers ?? parseFillerList(fillers)).join(', '))
      toast.success('Preferencias de procesamiento guardadas.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar las preferencias.')
    } finally {
      setSaving(false)
    }
  }, [browserDiarization, cleanup, diarization, fillers, toast, vocabulary])

  return {
    vocabulary,
    setVocabulary,
    fillers,
    setFillers,
    cleanup,
    setCleanup,
    diarization,
    setDiarization,
    browserDiarization,
    setBrowserDiarization,
    saving,
    save,
  }
}
