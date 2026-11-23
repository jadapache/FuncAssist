import React, { useRef, useState } from 'react'
import { Loader2, Pencil, Scissors, UserPlus, X } from 'lucide-react'
import type { TranscriptionSegment } from '../api/transcriptionApi'
import { formatTimestamp } from '../utils/time'
import { speakerKey } from '../utils/turns'
import type { SpeakerEntry } from '../utils/speakers'

interface SegmentEditModalProps {
  segment: TranscriptionSegment
  speakers: SpeakerEntry[]
  isSaving: boolean
  onClose: () => void
  onSaveText: (text: string) => Promise<boolean>
  onAssignSpeaker: (speakerId: string) => Promise<boolean>
  onNewSpeaker: (name: string) => Promise<boolean>
  onSplit: (at: number) => Promise<boolean>
}

/** Correct the text of one segment, move it to another speaker or split it at the cursor. */
export const SegmentEditModal: React.FC<SegmentEditModalProps> = ({
  segment,
  speakers,
  isSaving,
  onClose,
  onSaveText,
  onAssignSpeaker,
  onNewSpeaker,
  onSplit,
}) => {
  const currentSpeaker = speakerKey(segment)
  const [text, setText] = useState(segment.text)
  const [targetSpeaker, setTargetSpeaker] = useState(currentSpeaker)
  const [newSpeakerName, setNewSpeakerName] = useState('')
  const [splitAt, setSplitAt] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const textChanged = text.trim() !== segment.text.trim()
  const canSplit = !textChanged && splitAt !== null && splitAt > 0 && splitAt < segment.text.length

  const updateCaret = () => {
    const element = textareaRef.current
    if (element) setSplitAt(element.selectionStart)
  }

  const run = async (action: () => Promise<boolean>) => {
    if (await action()) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 space-y-5"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Pencil className="h-4 w-4 text-[#002777]" />
            <span>Editar fragmento [{formatTimestamp(segment.start)}]</span>
          </h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 cursor-pointer" title="Cerrar">
            <X className="h-4 w-4" />
          </button>
        </div>

        <section className="space-y-2">
          <label htmlFor="segment-text" className="text-xs font-bold text-slate-700">
            Texto
          </label>
          <textarea
            id="segment-text"
            ref={textareaRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onSelect={updateCaret}
            onClick={updateCaret}
            onKeyUp={updateCaret}
            rows={4}
            className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777]"
          />
          {segment.text_raw && segment.text_raw !== segment.text && (
            <p className="text-[11px] text-slate-400">
              <span className="font-semibold">Literal:</span> {segment.text_raw}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              disabled={!canSplit || isSaving}
              onClick={() => splitAt !== null && void run(() => onSplit(splitAt))}
              className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 cursor-pointer"
              title={
                textChanged
                  ? 'Guarda el texto antes de dividir el fragmento'
                  : 'Coloca el cursor donde empieza la segunda parte'
              }
            >
              <Scissors className="h-3.5 w-3.5" />
              Dividir en el cursor
            </button>
            <button
              type="button"
              disabled={!textChanged || !text.trim() || isSaving}
              onClick={() => void run(() => onSaveText(text.trim()))}
              className="btn-primary px-3 py-1.5 text-xs rounded-xl font-bold disabled:opacity-40 cursor-pointer"
            >
              Guardar texto
            </button>
          </div>
        </section>

        <section className="space-y-2 pt-3 border-t border-slate-100">
          <label htmlFor="segment-speaker" className="text-xs font-bold text-slate-700">
            Asignar a…
          </label>
          <div className="flex gap-2">
            <select
              id="segment-speaker"
              value={targetSpeaker}
              onChange={(event) => setTargetSpeaker(event.target.value)}
              className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
            >
              {speakers.map((speaker) => (
                <option key={speaker.id} value={speaker.id}>
                  {speaker.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={targetSpeaker === currentSpeaker || isSaving}
              onClick={() => void run(() => onAssignSpeaker(targetSpeaker))}
              className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 cursor-pointer"
            >
              Asignar
            </button>
          </div>
        </section>

        <section className="space-y-2">
          <label htmlFor="segment-new-speaker" className="text-xs font-bold text-slate-700">
            Nuevo hablante
          </label>
          <div className="flex gap-2">
            <input
              id="segment-new-speaker"
              type="text"
              value={newSpeakerName}
              onChange={(event) => setNewSpeakerName(event.target.value)}
              placeholder="Nombre del interlocutor"
              className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
            />
            <button
              type="button"
              disabled={!newSpeakerName.trim() || isSaving}
              onClick={() => void run(() => onNewSpeaker(newSpeakerName.trim()))}
              className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 flex items-center gap-1.5 cursor-pointer"
            >
              <UserPlus className="h-3.5 w-3.5" />
              Crear y asignar
            </button>
          </div>
        </section>

        {isSaving && (
          <p className="flex items-center gap-2 text-[11px] text-slate-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
          </p>
        )}
      </div>
    </div>
  )
}
