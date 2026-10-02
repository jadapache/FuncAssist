import type { FormEvent } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Coins,
  Cpu,
  Download,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mic,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import type { AISettings, LocalWhisperModelInfo, ModelCatalogItem } from '../../api/client'
import { BUILT_IN_WHISPER_MODELS } from './constants'

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
  localWhisperModels = [],
  downloadingWhisperId = null,
  deletingWhisperId = null,
  fetchingWhisperModels = false,
  fetchLocalWhisperModels,
  handleDownloadWhisperModel,
  handleDeleteWhisperModel,
}: VoiceAudioSectionProps) => {
  const isGroq = voiceAudioProvider === 'groq'
  const isOpenAI = voiceAudioProvider === 'openai'
  const isBuiltIn = voiceAudioProvider === 'builtin' || voiceAudioProvider === 'local'

  const selectedModelInfo = catalogModels.find(
    (m) => m.provider === voiceAudioProvider && m.id === voiceAudioModel,
  )

  const isGroqKeyConfigured = Boolean(ai?.transcription_groq_api_key_set || ai?.groq_api_key_set)
  const isOpenaiKeyConfigured = Boolean(ai?.transcription_openai_api_key_set || ai?.openai_api_key_set)

  const builtinFromCatalog = catalogModels.filter(
    (m) => m.task_type === 'transcription' && (m.provider === 'builtin' || m.provider === 'local'),
  )
  const localList = builtinFromCatalog.length > 0 ? builtinFromCatalog : BUILT_IN_WHISPER_MODELS

  const cloudModels = catalogModels.filter(
    (m) => m.task_type === 'transcription' && m.provider === voiceAudioProvider,
  )

  return (
    <div className="card space-y-6 border border-slate-200 bg-white p-6 md:p-8 shadow-xs rounded-2xl transition-all">
      <div
        onClick={() => setIsVoiceAudioOpen(!isVoiceAudioOpen)}
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4 cursor-pointer select-none"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-blue-100 text-[#002777]">
            <Mic className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Modelo de Transcripción y Comandos de Voz</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Configura el motor Whisper (Local integrado o Cloud) y gestiona los modelos instalados en tu equipo.
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
          {/* Selectores de Proveedor y Tipo de Motor */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-800 block">
              Proveedor del Motor de Transcripción
            </label>
            <select
              value={voiceAudioProvider}
              onChange={(e) => {
                const newP = e.target.value
                setVoiceAudioProvider(newP)
                if (newP === 'builtin' || newP === 'local') {
                  if (!voiceAudioModel || voiceAudioModel.startsWith('whisper-')) {
                    setVoiceAudioModel('base')
                  }
                } else if (newP === 'groq') {
                  if (!voiceAudioModel || !voiceAudioModel.startsWith('whisper-')) {
                    setVoiceAudioModel('whisper-large-v3')
                  }
                } else if (newP === 'openai') {
                  if (!voiceAudioModel || voiceAudioModel !== 'whisper-1') {
                    setVoiceAudioModel('whisper-1')
                  }
                }
              }}
              className="input-field text-sm font-medium text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2.5 px-3"
            >
              <option value="builtin">Whisper Integrado (Local / Ejecución en tu equipo sin costo)</option>
              <option value="groq">Groq Cloud (Whisper LPU Ultrarrápido - Free Tier)</option>
              <option value="openai">OpenAI API (Whisper Oficial Cloud)</option>
            </select>
          </div>

          {/* CASO 1: WHISPER LOCAL INTEGRADO */}
          {isBuiltIn && (
            <div className="space-y-4 pt-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-blue-50 border border-blue-200 text-xs text-[#002777]">
                <div className="flex items-center gap-2.5">
                  <Cpu className="h-4 w-4 shrink-0 text-[#002777]" />
                  <span className="font-medium">
                    El procesamiento local ejecuta Whisper directamente en tu GPU/CPU sin enviar audio a internet. Puedes descargar y gestionar los modelos en tu disco.
                  </span>
                </div>
                {fetchLocalWhisperModels && (
                  <button
                    type="button"
                    onClick={() => void fetchLocalWhisperModels()}
                    disabled={fetchingWhisperModels}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white border border-blue-200 text-[11px] font-semibold text-[#002777] hover:bg-blue-50 transition shrink-0 cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className={['h-3 w-3', fetchingWhisperModels ? 'animate-spin' : ''].join(' ')} />
                    Actualizar estado
                  </button>
                )}
              </div>

              <div className="space-y-3">
                {localList.map((m) => {
                  const isSelected = voiceAudioModel === m.id || voiceAudioModel === `whisper-${m.id}`
                  const cleanId = m.id.replace('whisper-', '')
                  const localInfo = localWhisperModels.find((lm) => lm.id === cleanId || lm.id === m.id)
                  const isDownloaded = Boolean(
                    ('is_downloaded' in m && m.is_downloaded) || localInfo?.is_downloaded,
                  )
                  const isDownloading = downloadingWhisperId === cleanId || downloadingWhisperId === m.id
                  const isDeleting = deletingWhisperId === cleanId || deletingWhisperId === m.id
                  const catalogMb = 'disk_size_mb' in m && typeof m.disk_size_mb === 'number' ? m.disk_size_mb : 0
                  const diskSizeStr =
                    localInfo && localInfo.disk_size_mb > 0
                      ? `${localInfo.disk_size_mb} MB`
                      : catalogMb > 0
                      ? `${catalogMb} MB`
                      : m.size || '75 MB'

                  return (
                    <div
                      key={m.id}
                      onClick={() => setVoiceAudioModel(m.id)}
                      className={[
                        'flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl transition-all cursor-pointer',
                        isSelected
                          ? 'border-2 border-[#002777] bg-blue-50/20 shadow-xs'
                          : 'border border-slate-200 bg-white hover:border-slate-300',
                      ].join(' ')}
                    >
                      <div className="space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <h5 className="font-bold text-slate-900 text-base">{m.name}</h5>
                          {isDownloaded ? (
                            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Descargado ({diskSizeStr})
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200">
                              No descargado ({m.size || 'Local'})
                            </span>
                          )}
                          {isSelected && (
                            <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
                              Seleccionado
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
                          {m.description}
                        </p>
                        <p className="text-xs text-slate-400 font-medium pt-0.5 flex items-center gap-2">
                          <span>Tamaño: {m.size || 'Variable'}</span>
                          <span>•</span>
                          <span>Precisión: {m.accuracy || 'Estándar'}</span>
                        </p>
                      </div>

                      <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        {isDownloaded ? (
                          <>
                            {handleDeleteWhisperModel && (
                              <button
                                type="button"
                                disabled={isDeleting}
                                onClick={() => void handleDeleteWhisperModel(cleanId)}
                                title="Eliminar archivo del modelo para liberar espacio en disco"
                                className="inline-flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition cursor-pointer disabled:opacity-50"
                              >
                                {isDeleting ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="h-3.5 w-3.5" />
                                )}
                                Borrar
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => setVoiceAudioModel(m.id)}
                              className={[
                                'px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer',
                                isSelected
                                  ? 'bg-[#002777] text-white font-bold'
                                  : 'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700',
                              ].join(' ')}
                            >
                              {isSelected ? 'Activo' : 'Seleccionar'}
                            </button>
                          </>
                        ) : (
                          <>
                            {handleDownloadWhisperModel && (
                              <button
                                type="button"
                                disabled={isDownloading}
                                onClick={() => void handleDownloadWhisperModel(cleanId)}
                                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-[#002777] bg-blue-50 hover:bg-blue-100 border border-blue-200 transition cursor-pointer disabled:opacity-50"
                              >
                                {isDownloading ? (
                                  <>
                                    <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />
                                    Descargando...
                                  </>
                                ) : (
                                  <>
                                    <Download className="h-3.5 w-3.5 text-[#002777]" />
                                    Descargar ({m.size || 'Modelo'})
                                  </>
                                )}
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => setVoiceAudioModel(m.id)}
                              className={[
                                'px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer',
                                isSelected
                                  ? 'bg-[#002777] text-white font-bold'
                                  : 'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700',
                              ].join(' ')}
                            >
                              {isSelected ? 'Activo' : 'Seleccionar'}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* CASO 2 & 3: PROVEEDORES CLOUD (GROQ / OPENAI) */}
          {(isGroq || isOpenAI) && (
            <div className="space-y-5 pt-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-800 block">
                  Modelo en la Nube
                </label>
                <select
                  value={voiceAudioModel}
                  onChange={(e) => setVoiceAudioModel(e.target.value)}
                  className="input-field text-sm font-medium text-slate-900 border border-slate-300 rounded-xl"
                >
                  {cloudModels.length > 0 ? (
                    cloudModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))
                  ) : isGroq ? (
                    <>
                      <option value="whisper-large-v3">Whisper Large v3 (Recomendado / Máxima Precisión)</option>
                      <option value="whisper-large-v3-turbo">Whisper Large v3 Turbo (Velocidad Extrema)</option>
                    </>
                  ) : (
                    <option value="whisper-1">Whisper 1 (OpenAI Cloud Audio API)</option>
                  )}
                </select>
              </div>

              {/* Resumen del modelo de voz seleccionado */}
              <div className="rounded-xl border border-blue-100 bg-slate-50/60 p-4 space-y-2 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-900">
                      {selectedModelInfo?.name || (isGroq ? 'Whisper Large v3 (Groq)' : 'Whisper 1 (OpenAI)')}
                    </span>
                    <code className="text-[11px] font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                      {voiceAudioModel}
                    </code>
                  </div>
                  {isGroq ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                      <Sparkles className="h-3 w-3" /> Gratuito (Free Tier)
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-[10px] font-bold text-[#002777]">
                      <Coins className="h-3 w-3" /> De Pago ($0.006 / min)
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-600 pt-1">
                  <div>
                    <span className="text-slate-400">Tipo de motor:</span>{' '}
                    <span className="font-semibold text-slate-700">Audio Speech-to-Text</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Latencia estimada:</span>{' '}
                    <span className="font-semibold text-slate-700">
                      {isGroq ? 'Ultrarrápida (~10x tiempo real)' : 'Media (~2-5s)'}
                    </span>
                  </div>
                  <div className="sm:col-span-2">
                    <span className="text-slate-400">Diarización y resumen:</span>{' '}
                    <span className="font-semibold text-slate-700">
                      Compatible con segmentación de participantes y extracción de requerimientos
                    </span>
                  </div>
                </div>
              </div>

              {/* Credenciales de API */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                    <Lock className="h-3.5 w-3.5 text-slate-500" />
                    {isGroq ? 'Groq API Key (Voz y Transcripción)' : 'OpenAI API Key (Voz y Transcripción)'}
                  </label>
                  {(isGroq ? isGroqKeyConfigured : isOpenaiKeyConfigured) && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 border border-emerald-200">
                      <Check className="h-3 w-3" /> Configurada
                    </span>
                  )}
                </div>

                <div className="relative">
                  <input
                    type={showTranscriptionKey ? 'text' : 'password'}
                    value={isGroq ? transcriptionGroqKey : transcriptionOpenaiKey}
                    onChange={(e) =>
                      isGroq
                        ? setTranscriptionGroqKey(e.target.value)
                        : setTranscriptionOpenaiKey(e.target.value)
                    }
                    placeholder={
                      isGroq
                        ? isGroqKeyConfigured
                          ? '•••••••••••••••••••••••• (dejar en blanco para conservar actual)'
                          : 'gsk_...'
                        : isOpenaiKeyConfigured
                        ? '•••••••••••••••••••••••• (dejar en blanco para conservar actual)'
                        : 'sk-...'
                    }
                    className="input-field pr-10 text-sm font-mono text-slate-900 border border-slate-300 rounded-xl"
                  />
                  <button
                    type="button"
                    onClick={() => setShowTranscriptionKey(!showTranscriptionKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition cursor-pointer"
                  >
                    {showTranscriptionKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="text-[11px] text-slate-500">
                  {isGroq ? (
                    <>
                      Obtén tu clave gratuita en{' '}
                      <a
                        href="https://console.groq.com/keys"
                        target="_blank"
                        rel="noreferrer"
                        className="text-[#002777] font-semibold underline hover:text-blue-800"
                      >
                        console.groq.com/keys
                      </a>
                    </>
                  ) : (
                    <>
                      Obtén tu clave en{' '}
                      <a
                        href="https://platform.openai.com/api-keys"
                        target="_blank"
                        rel="noreferrer"
                        className="text-[#002777] font-semibold underline hover:text-blue-800"
                      >
                        platform.openai.com/api-keys
                      </a>
                    </>
                  )}
                </p>
              </div>
            </div>
          )}

          {/* Botón de Guardar Panel */}
          <div className="flex justify-end pt-4 border-t border-slate-100">
            <button
              type="button"
              disabled={savingAi}
              onClick={() => void handleVoiceAudioSave()}
              className="inline-flex items-center gap-2 rounded-xl bg-[#002777] px-6 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#001f5f] transition disabled:opacity-50 cursor-pointer"
            >
              {savingAi ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  Guardando configuración...
                </>
              ) : (
                'Guardar Configuración de Voz'
              )}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
