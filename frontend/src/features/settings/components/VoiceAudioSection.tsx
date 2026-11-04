import type { FormEvent } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Mic,
  RefreshCw,
} from 'lucide-react'
import type { AISettings, ModelCatalogItem } from '../../../api/client'
import { LocalVoiceModelsList } from './voice/LocalVoiceModelsList'
import { CloudVoiceModelSelector } from './voice/CloudVoiceModelSelector'
import { DEFAULT_BROWSER_ASR_MODEL } from '../../ai/catalogs/clientCatalog'

export type VoiceAudioSectionProps = {
  ai: AISettings | null
  voiceAudioProvider: string
  setVoiceAudioProvider: (p: string) => void
  voiceAudioModel: string
  setVoiceAudioModel: (m: string) => void
  isVoiceAudioOpen: boolean
  setIsVoiceAudioOpen: (open: boolean) => void
  catalogModels: ModelCatalogItem[]
  transcriptionGroqKey: string
  setTranscriptionGroqKey: (k: string) => void
  transcriptionOpenaiKey: string
  setTranscriptionOpenaiKey: (k: string) => void
  showTranscriptionKey: boolean
  setShowTranscriptionKey: (show: boolean) => void
  savingAi: boolean
  handleVoiceAudioSave: (e?: FormEvent) => Promise<void>
}

export const VoiceAudioSection = ({
  ai,
  voiceAudioProvider,
  setVoiceAudioProvider,
  voiceAudioModel,
  setVoiceAudioModel,
  isVoiceAudioOpen,
  setIsVoiceAudioOpen,
  catalogModels,
  transcriptionGroqKey,
  setTranscriptionGroqKey,
  transcriptionOpenaiKey,
  setTranscriptionOpenaiKey,
  showTranscriptionKey,
  setShowTranscriptionKey,
  savingAi,
  handleVoiceAudioSave,
}: VoiceAudioSectionProps) => {
  const isBrowserMode =
    voiceAudioProvider === 'browser_asr' ||
    voiceAudioProvider === 'local' ||
    voiceAudioProvider === 'builtin'

  return (
    <form
      onSubmit={(e) => void handleVoiceAudioSave(e)}
      className="card space-y-6 border border-slate-200 bg-white p-6 md:p-8 shadow-sm rounded-2xl transition-all"
    >
      <div
        onClick={() => setIsVoiceAudioOpen(!isVoiceAudioOpen)}
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4 cursor-pointer select-none"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-blue-100 text-[#002777]">
            <Mic className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Modelos de Transcripción y Comandos de Voz</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Configura la ejecución en el navegador (WebGPU / Web Worker) o mediante APIs en la nube.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
          {!isVoiceAudioOpen && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
              Activo: <span className="font-mono text-[11px] text-[#002777] font-bold">{voiceAudioProvider} • {voiceAudioModel}</span>
            </span>
          )}
          <div
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
            title={isVoiceAudioOpen ? 'Plegar panel' : 'Desplegar panel'}
          >
            {isVoiceAudioOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </div>
        </div>
      </div>

      {isVoiceAudioOpen && (
        <>
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-800 block">
              Entorno de Ejecución de Transcripción
            </label>
            <select
              value={isBrowserMode ? 'local' : voiceAudioProvider}
              onChange={(e) => {
                const newP = e.target.value
                setVoiceAudioProvider(newP)
                if (newP === 'local') {
                  setVoiceAudioModel(DEFAULT_BROWSER_ASR_MODEL)
                } else if (newP === 'groq') {
                  setVoiceAudioModel('whisper-large-v3')
                } else if (newP === 'openai') {
                  setVoiceAudioModel('whisper-1')
                }
              }}
              className="input-field text-sm font-medium text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2.5 px-3"
            >
              <option value="local">En este navegador (Transformers.js / WebGPU)</option>
              <option value="groq">Groq (API externa)</option>
              <option value="openai">OpenAI (API externa)</option>
            </select>
          </div>

          {isBrowserMode && (
            <LocalVoiceModelsList
              model={voiceAudioModel}
              setModel={setVoiceAudioModel}
            />
          )}

          {['groq', 'openai'].includes(voiceAudioProvider) && (
            <CloudVoiceModelSelector
              provider={voiceAudioProvider}
              model={voiceAudioModel}
              setModel={setVoiceAudioModel}
              catalogModels={catalogModels}
              ai={ai}
              transcriptionGroqKey={transcriptionGroqKey}
              setTranscriptionGroqKey={setTranscriptionGroqKey}
              transcriptionOpenaiKey={transcriptionOpenaiKey}
              setTranscriptionOpenaiKey={setTranscriptionOpenaiKey}
              showTranscriptionKey={showTranscriptionKey}
              setShowTranscriptionKey={setShowTranscriptionKey}
            />
          )}

          <div className="flex flex-wrap items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <button
              type="submit"
              disabled={savingAi}
              className="bg-[#002777] hover:bg-[#001f5f] text-white font-bold px-6 py-2.5 rounded-xl shadow-xs transition flex items-center gap-2 cursor-pointer text-sm disabled:opacity-50"
            >
              {savingAi ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              <span>Guardar Modelo de Transcripción</span>
            </button>
          </div>
        </>
      )}
    </form>
  )
}
