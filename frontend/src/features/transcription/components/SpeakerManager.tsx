import React from 'react'
import { Users } from 'lucide-react'

interface SpeakerManagerProps {
  isOpen: boolean
  speakerMap: Record<string, string>
  onSpeakerChange: (speaker: string, newName: string) => void
  onSave: () => void
  onClose: () => void
}

export const SpeakerManager: React.FC<SpeakerManagerProps> = ({
  isOpen,
  speakerMap,
  onSpeakerChange,
  onSave,
  onClose,
}) => {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-fade-in">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Users className="h-4 w-4 text-[#002777]" />
            <span>Renombrar Interlocutores</span>
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-xs cursor-pointer"
          >
            ✕
          </button>
        </div>

        <p className="text-xs text-slate-500">
          Asigna nombres reales a los identificadores detectados por el motor de diarización:
        </p>

        <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
          {Object.keys(speakerMap).map((spk) => (
            <div key={spk} className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-600 w-32 shrink-0 truncate">
                {spk}:
              </span>
              <input
                type="text"
                value={speakerMap[spk]}
                onChange={(e) => onSpeakerChange(spk, e.target.value)}
                className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777]"
              />
            </div>
          ))}
        </div>

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
            onClick={onSave}
            className="btn-primary px-4 py-1.5 text-xs rounded-xl font-bold cursor-pointer"
          >
            Guardar Nombres
          </button>
        </div>
      </div>
    </div>
  )
}
