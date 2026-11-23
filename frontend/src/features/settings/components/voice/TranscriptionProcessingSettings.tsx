import { Check, RefreshCw, Wand2 } from 'lucide-react'
import type { AISettings } from '../../../../api/client'
import {
  MAX_VOCABULARY_CHARS,
  useTranscriptionProcessingSettings,
  type CleanupMode,
  type DiarizationMode,
} from './useTranscriptionProcessingSettings'

const CLEANUP_OPTIONS: Array<{ value: CleanupMode; label: string; description: string }> = [
  {
    value: 'rules',
    label: 'Por reglas (recomendado)',
    description: 'Quita vacilaciones (eh, mmm), repeticiones y coletillas como «¿no?» sin tocar el contenido.',
  },
  {
    value: 'llm',
    label: 'Con IA',
    description:
      'Además usa tu modelo de redacción en la nube para limpiar muletillas ambiguas. Si no tienes uno en la nube, se aplican las reglas.',
  },
  { value: 'off', label: 'Desactivada', description: 'Guarda el texto tal como lo devuelve el modelo.' },
]

/** Transcription post-processing preferences shown inside the voice settings card. */
export const TranscriptionProcessingSettings = ({ ai }: { ai: AISettings | null }) => {
  const settings = useTranscriptionProcessingSettings(ai)

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
      <div className="flex items-center gap-2">
        <Wand2 className="h-4 w-4 text-[#002777]" />
        <h4 className="text-sm font-bold text-slate-900">Procesamiento del texto</h4>
      </div>
      <p className="text-xs text-slate-500">
        Siempre se guarda también el texto literal; en la transcripción puedes alternar entre «Limpio» y «Literal».
      </p>

      <div className="space-y-2">
        <span className="text-xs font-semibold text-slate-800 block">Limpieza de muletillas</span>
        <div className="space-y-1.5">
          {CLEANUP_OPTIONS.map((option) => (
            <label key={option.value} className="flex items-start gap-2 text-xs text-slate-700 cursor-pointer">
              <input
                type="radio"
                name="transcription-cleanup"
                value={option.value}
                checked={settings.cleanup === option.value}
                onChange={() => settings.setCleanup(option.value)}
                className="mt-0.5 h-3.5 w-3.5 text-[#002777] focus:ring-[#002777]/30"
              />
              <span>
                <span className="font-semibold">{option.label}.</span> {option.description}
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="transcription-fillers" className="text-xs font-semibold text-slate-800 block">
          Muletillas adicionales
        </label>
        <textarea
          id="transcription-fillers"
          value={settings.fillers}
          onChange={(event) => settings.setFillers(event.target.value)}
          rows={2}
          disabled={settings.cleanup === 'off'}
          placeholder="Separadas por comas: digamos, o sea, tipo"
          className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="transcription-vocabulary" className="text-xs font-semibold text-slate-800 block">
          Vocabulario del dominio
        </label>
        <textarea
          id="transcription-vocabulary"
          value={settings.vocabulary}
          onChange={(event) => settings.setVocabulary(event.target.value)}
          maxLength={MAX_VOCABULARY_CHARS}
          rows={3}
          placeholder="Nombres de productos, siglas y personas que suelen aparecer en las reuniones"
          className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
        />
        <p className="text-[11px] text-slate-400">
          {settings.vocabulary.length}/{MAX_VOCABULARY_CHARS}. Ayuda a Whisper a escribir bien los términos propios. No se
          aplica con la diarización de OpenAI.
        </p>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="transcription-diarization" className="text-xs font-semibold text-slate-800 block">
          Identificación de interlocutores
        </label>
        <select
          id="transcription-diarization"
          value={settings.diarization}
          onChange={(event) => settings.setDiarization(event.target.value as DiarizationMode)}
          className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs"
        >
          <option value="auto">Automática (con OpenAI si hay clave configurada)</option>
          <option value="off">Desactivada (un único interlocutor)</option>
        </select>
        <label className="flex items-start gap-2 pt-1 text-xs text-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={settings.browserDiarization}
            onChange={(event) => settings.setBrowserDiarization(event.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300 text-[#002777] focus:ring-[#002777]/30"
          />
          <span>
            <span className="font-semibold">Identificar interlocutores también en el navegador.</span> Para las
            transcripciones locales: el audio no sale del equipo, pero la primera vez se descargan unos 30 MB de modelos y
            el proceso tarda más. Es el valor inicial; puedes cambiarlo en cada subida.
          </span>
        </label>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void settings.save()}
          disabled={settings.saving}
          className="flex items-center gap-2 rounded-xl border border-[#002777] px-4 py-2 text-xs font-bold text-[#002777] transition hover:bg-blue-50 disabled:opacity-50 cursor-pointer"
        >
          {settings.saving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
          Guardar preferencias de procesamiento
        </button>
      </div>
    </div>
  )
}
