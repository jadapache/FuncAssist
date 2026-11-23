import React, { useState } from 'react'
import { Loader2, Users } from 'lucide-react'
import type { SpeakersPatch } from '../api/transcriptionApi'
import { speakerDotClass, type SpeakerEntry } from '../utils/speakers'

interface SpeakerManagerProps {
  speakers: SpeakerEntry[]
  diarization?: string
  isSaving: boolean
  onSave: (patch: SpeakersPatch) => Promise<boolean>
  onClose: () => void
}

interface Draft {
  name: string
  mergeInto: string
}

/**
 * Rename and merge speakers. Drafts start from the saved speakers every time the dialog opens
 * (the parent mounts it only while open), so "Cancelar" discards every change.
 */
export const SpeakerManager: React.FC<SpeakerManagerProps> = ({ speakers, diarization, isSaving, onSave, onClose }) => {
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() =>
    Object.fromEntries(speakers.map((speaker) => [speaker.id, { name: speaker.name, mergeInto: '' }])),
  )
  const [error, setError] = useState<string | null>(null)

  const update = (id: string, change: Partial<Draft>) => {
    setError(null)
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...change } }))
  }

  const handleSave = async () => {
    const rename: Record<string, string> = {}
    const merge: Array<{ from: string; into: string }> = []
    for (const speaker of speakers) {
      const draft = drafts[speaker.id]
      if (!draft) continue
      if (draft.mergeInto) {
        if (drafts[draft.mergeInto]?.mergeInto) {
          setError('No se puede fusionar con un interlocutor que también se va a fusionar.')
          return
        }
        merge.push({ from: speaker.id, into: draft.mergeInto })
        continue
      }
      const name = draft.name.trim()
      if (!name) {
        setError('Los nombres no pueden quedar vacíos.')
        return
      }
      if (name !== speaker.name) rename[speaker.id] = name
    }
    if (merge.length === 0 && Object.keys(rename).length === 0) {
      onClose()
      return
    }
    const patch: SpeakersPatch = {}
    if (Object.keys(rename).length > 0) patch.rename = rename
    if (merge.length > 0) patch.merge = merge
    if (await onSave(patch)) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 space-y-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Users className="h-4 w-4 text-[#002777]" />
            <span>Interlocutores</span>
          </h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xs cursor-pointer">
            ✕
          </button>
        </div>

        <p className="text-xs text-slate-500">
          {diarization === 'none'
            ? 'Los hablantes no se identificaron automáticamente. Asigna nombres aquí y reparte los fragmentos con el lápiz de cada uno.'
            : 'Asigna nombres reales a los interlocutores detectados o fusiona los que sean la misma persona.'}
        </p>

        <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
          {speakers.map((speaker) => {
            const draft = drafts[speaker.id] || { name: speaker.name, mergeInto: '' }
            const others = speakers.filter((other) => other.id !== speaker.id)
            return (
              <div key={speaker.id} className="flex flex-wrap items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${speakerDotClass(speaker.colorIndex)}`} />
                <input
                  type="text"
                  value={draft.name}
                  disabled={Boolean(draft.mergeInto)}
                  onChange={(event) => update(speaker.id, { name: event.target.value })}
                  aria-label={`Nombre de ${speaker.name}`}
                  className="flex-1 min-w-[140px] px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777] disabled:opacity-50"
                />
                <span className="text-[10px] text-slate-400 w-16 shrink-0 text-right">
                  {speaker.segmentCount} {speaker.segmentCount === 1 ? 'fragm.' : 'fragms.'}
                </span>
                {others.length > 0 && (
                  <select
                    value={draft.mergeInto}
                    onChange={(event) => update(speaker.id, { mergeInto: event.target.value })}
                    aria-label={`Fusionar ${speaker.name} con`}
                    className="px-2 py-1.5 text-xs bg-white border border-slate-200 rounded-xl text-slate-600 focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
                  >
                    <option value="">No fusionar</option>
                    {others.map((other) => (
                      <option key={other.id} value={other.id}>
                        Fusionar con {drafts[other.id]?.name || other.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )
          })}
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl cursor-pointer"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={isSaving}
            className="btn-primary px-4 py-1.5 text-xs rounded-xl font-bold cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
          >
            {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Guardar cambios
          </button>
        </div>
      </div>
    </div>
  )
}
