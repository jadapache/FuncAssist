import { useCallback, useMemo, useState } from 'react'
import {
  transcriptionApi,
  type SegmentPatch,
  type SpeakersPatch,
  type TranscriptionMutationResponse,
  type TranscriptionResult,
  type TranscriptionSegment,
} from '../api/transcriptionApi'
import { listSpeakers } from '../utils/speakers'
import type { ToastApi } from './useTranscriptionJobRunners'
import { useLatest } from './useLatest'

interface SpeakerEditingDeps {
  record: TranscriptionResult | null
  setRecord: (record: TranscriptionResult) => void
  onRecordSaved: (record: TranscriptionResult) => void
  toast: ToastApi
  /** Editing is disabled while a job is rewriting the transcription. */
  disabled: boolean
}

/**
 * Speaker and segment edits. Every change goes to the server and the studio is rebuilt from the
 * transcription it returns, so the speaker list never holds stale keys.
 */
export function useSpeakerEditing(deps: SpeakerEditingDeps) {
  const { record, disabled } = deps
  const depsRef = useLatest(deps)
  const [isSaving, setIsSaving] = useState(false)
  const [managerOpen, setManagerOpen] = useState(false)

  const speakers = useMemo(() => listSpeakers(record), [record])
  const canEdit = Boolean(
    record && !disabled && record.segments.length > 0 && record.segments.every((segment) => Boolean(segment.id)),
  )

  const apply = useCallback(
    async (request: () => Promise<TranscriptionMutationResponse>, successMessage?: string): Promise<boolean> => {
      setIsSaving(true)
      try {
        const response = await request()
        depsRef.current.setRecord(response.transcription)
        depsRef.current.onRecordSaved(response.transcription)
        if (successMessage) depsRef.current.toast.success(successMessage)
        return true
      } catch (err) {
        depsRef.current.toast.error(
          err instanceof Error ? err.message : 'Error desconocido.',
          'No se pudo guardar el cambio',
        )
        return false
      } finally {
        setIsSaving(false)
      }
    },
    [depsRef],
  )

  const recordId = record?.id

  const saveSpeakers = useCallback(
    (patch: SpeakersPatch) => {
      if (!recordId) return Promise.resolve(false)
      return apply(() => transcriptionApi.updateSpeakers(recordId, patch), 'Interlocutores actualizados.')
    },
    [apply, recordId],
  )

  const patchSegment = useCallback(
    (segmentId: string, patch: SegmentPatch, successMessage?: string) => {
      if (!recordId) return Promise.resolve(false)
      return apply(() => transcriptionApi.updateSegment(recordId, segmentId, patch), successMessage)
    },
    [apply, recordId],
  )

  const splitSegment = useCallback(
    (segmentId: string, at: number) => {
      if (!recordId) return Promise.resolve(false)
      return apply(() => transcriptionApi.splitSegment(recordId, segmentId, at), 'Segmento dividido.')
    },
    [apply, recordId],
  )

  /** Marks are toggled optimistically and reverted if the server rejects the change. */
  const toggleMarked = useCallback(
    async (segment: TranscriptionSegment) => {
      const current = depsRef.current.record
      if (!current || !segment.id) return
      const marked = !segment.marked
      const optimistic: TranscriptionResult = {
        ...current,
        segments: current.segments.map((item) => (item.id === segment.id ? { ...item, marked } : item)),
      }
      depsRef.current.setRecord(optimistic)
      try {
        const response = await transcriptionApi.updateSegment(current.id, segment.id, { marked })
        depsRef.current.setRecord(response.transcription)
        depsRef.current.onRecordSaved(response.transcription)
      } catch (err) {
        depsRef.current.setRecord(current)
        depsRef.current.toast.error(err instanceof Error ? err.message : 'Error desconocido.', 'No se pudo marcar el segmento')
      }
    },
    [depsRef],
  )

  return {
    speakers,
    canEdit,
    isSaving,
    managerOpen,
    setManagerOpen,
    saveSpeakers,
    patchSegment,
    splitSegment,
    toggleMarked,
  }
}
