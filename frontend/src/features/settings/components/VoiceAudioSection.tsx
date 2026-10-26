import type { FormEvent } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Mic,
  RefreshCw,
} from 'lucide-react'
import type { AISettings, LocalWhisperModelInfo, ModelCatalogItem } from '../../../api/client'
import { LocalVoiceModelsList, type LocalVoiceModelItem } from './voice/LocalVoiceModelsList'
import { CloudVoiceModelSelector } from './voice/CloudVoiceModelSelector'

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
  localWhisperModels?: LocalWhisperModelInfo[]
  downloadingWhisperId?: string | null
  deletingWhisperId?: string | null
  fetchingWhisperModels?: boolean
  fetchLocalWhisperModels?: () => Promise<void>
  handleDownloadWhisperModel?: (modelId: string) => Promise<void>
  handleDeleteWhisperModel?: (modelId: string) => Promise<void>
  downloadTasks?: Record<string, { progress: number; speedOrSize?: string | null; stageText?: string }>
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
  // Construcción de la lista de modelos de voz locales integrados
  const builtinFromCatalog = catalogModels.filter(
    (m) =>
      m.task_type === 'transcription' &&
      (m.provider === 'builtin' ||
        m.provider === 'local' ||
        m.provider === 'onnx'),
  )

  const DEFAULT_ONNX_MODELS: LocalVoiceModelItem[] = [
    {
      id: 'whisper-tiny',
      name: 'Whisper Tiny (ONNX Web / Ultra Rápido)',
      tag: 'onnx:whisper-tiny',
      description: 'Modelo Whisper optimizado para ONNX Web Runtime. Ultraligero (~40 MB), ideal para CPU WASM o transcribir con mínimo consumo.',
      size: '~40 MB',
      accuracy: 'Básica (Ultra Rápido)',
      provider: 'onnx',
      engine: 'onnxruntime-web',
    },
    {
      id: 'whisper-base',
      name: 'Whisper Base (ONNX Web / Recomendado)',
      tag: 'onnx:whisper-base',
      description: 'Excelente balance entre velocidad y precisión para reuniones estándar. Funciona de manera fluida en WebGPU y CPU.',
      size: '~75 MB',
      accuracy: 'Estándar (Recomendado)',
      provider: 'onnx',
      engine: 'onnxruntime-web',
    },
    {
      id: 'whisper-small',
      name: 'Whisper Small (ONNX Web / Alta Precisión)',
      tag: 'onnx:whisper-small',
      description: 'Mayor fidelidad y precisión con acentos en español y terminología técnica. Recomendado con aceleración WebGPU.',
      size: '~250 MB',
      accuracy: 'Alta',
      provider: 'onnx',
      engine: 'onnxruntime-web',
    },
    {
      id: 'whisper-large-v3-turbo',
      name: 'Whisper Large v3 Turbo (ONNX Web / Máxima Precisión)',
      tag: 'onnx:whisper-large-v3-turbo',
      description: 'Modelo de máxima fidelidad multilingüe optimizado en ONNX para WebGPU.',
      size: '~800 MB',
      accuracy: 'Máxima',
      provider: 'onnx',
      engine: 'onnxruntime-web',
    },
  ]

  const localVoiceModelsList: LocalVoiceModelItem[] =
    builtinFromCatalog.length > 0
      ? builtinFromCatalog.map((m) => ({
          id: m.id,
          name: m.name,
          tag: m.raw_id || m.id,
          description: m.description,
          size: m.size || '~75 MB',
          accuracy: m.accuracy || 'Estándar',
          provider: 'onnx',
          engine: 'onnxruntime-web',
          is_downloaded: true,
          disk_size_mb: m.disk_size_mb,
        }))
      : DEFAULT_ONNX_MODELS

  const isBuiltIn =
    voiceAudioProvider === 'builtin' ||
    voiceAudioProvider === 'local' ||
    voiceAudioProvider === 'onnx'

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
              Configura el motor de transcripción (ONNX Runtime, Faster Whisper, Moonshine, Whisper o Cloud) y gestiona los modelos offline instalados en tu equipo.
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
          {/* Selector de Proveedor del Motor de Transcripción */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-800 block">
              Proveedor del Motor de Transcripción
            </label>
            <select
              value={isBuiltIn ? 'builtin' : voiceAudioProvider}
              onChange={(e) => {
                const newP = e.target.value
                setVoiceAudioProvider(newP)
                if (newP === 'builtin') {
                  if (!voiceAudioModel || voiceAudioModel.startsWith('whisper-large') || voiceAudioModel === 'whisper-1') {
                    setVoiceAudioModel('base')
                  }
                } else if (newP === 'groq') {
                  setVoiceAudioModel('whisper-large-v3')
                } else if (newP === 'openai') {
                  setVoiceAudioModel('whisper-1')
                }
              }}
              className="input-field text-sm font-medium text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2.5 px-3"
            >
              <option value="builtin">IA Integrada (Local)</option>
              <option value="groq">Groq (API)</option>
              <option value="openai">OpenAI (API)</option>
            </select>
          </div>

          {/* CASO 1: MODELOS INTEGRADOS LOCALES */}
          {isBuiltIn && (
            <LocalVoiceModelsList
              localVoiceModelsList={localVoiceModelsList}
              model={voiceAudioModel}
              setModel={setVoiceAudioModel}
            />
          )}

          {/* CASO 2: PROVEEDORES CLOUD (GROQ, OPENAI) */}
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

          {/* Botón Guardar */}
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
