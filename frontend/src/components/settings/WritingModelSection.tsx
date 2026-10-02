import type { FormEvent } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Coins,
  Download,
  Eye,
  EyeOff,
  FileText,
  Gauge,
  Loader2,
  Lock,
  RefreshCw,
  RotateCw,
  Sparkles,
  Trash2,
  Zap,
} from 'lucide-react'
import type { AISettings, ModelCatalogItem } from '../../api/client'
import { BUILT_IN_MODELS, OLLAMA_RECOMMENDED } from './constants'

export type WritingModelSectionProps = {
  ai: AISettings | null
  provider: string
  setProvider: (p: string) => void
  model: string
  setModel: (m: string) => void
  isWritingOpen: boolean
  setIsWritingOpen: (open: boolean) => void
  showEndpointSection: boolean
  setShowEndpointSection: (show: boolean) => void
  ollamaUrl: string
  setOllamaUrl: (url: string) => void
  ollamaOnline: boolean | null
  ollamaModels: string[]
  fetchingModels: boolean
  fetchOllamaModels: (url?: string, isUserAction?: boolean) => Promise<void>
  isPulling: boolean
  pullingModelTag: string | null
  deletingModelTag?: string | null
  pullStatusMsg: string | null
  handlePullModel: (tag: string) => Promise<void>
  handleDeleteModel?: (tag: string) => Promise<void>
  isModelDownloaded: (tag: string) => boolean
  catalogModels: ModelCatalogItem[]
  groqKey: string
  setGroqKey: (k: string) => void
  geminiKey: string
  setGeminiKey: (k: string) => void
  openaiKey: string
  setOpenaiKey: (k: string) => void
  claudeKey: string
  setClaudeKey: (k: string) => void
  showKey: boolean
  setShowKey: (show: boolean) => void
  savingAi: boolean
  testingConnection: boolean
  handleAiSave: (e?: FormEvent) => Promise<void>
  handleTestConnection: () => Promise<void>
}

export const WritingModelSection = ({
  ai,
  provider,
  setProvider,
  model,
  setModel,
  isWritingOpen,
  setIsWritingOpen,
  showEndpointSection,
  setShowEndpointSection,
  ollamaUrl,
  setOllamaUrl,
  ollamaOnline,
  ollamaModels,
  fetchingModels,
  fetchOllamaModels,
  isPulling,
  pullingModelTag,
  deletingModelTag,
  pullStatusMsg,
  handlePullModel,
  handleDeleteModel,
  isModelDownloaded,
  catalogModels,
  groqKey,
  setGroqKey,
  geminiKey,
  setGeminiKey,
  openaiKey,
  setOpenaiKey,
  claudeKey,
  setClaudeKey,
  showKey,
  setShowKey,
  savingAi,
  testingConnection,
  handleAiSave,
  handleTestConnection,
}: WritingModelSectionProps) => {
  const builtinFromCatalog = catalogModels.filter(
    (m) => m.provider === 'builtin' && m.task_type === 'chat_writing',
  )
  const builtinModelsList =
    builtinFromCatalog.length > 0
      ? builtinFromCatalog.map((cm) => {
          const match = BUILT_IN_MODELS.find((bm) => bm.id === cm.id || bm.tag === cm.raw_id)
          return {
            id: cm.id,
            name: cm.name,
            tag: cm.raw_id || cm.id,
            description: cm.description,
            size: cm.size || match?.size || '~1.2 GiB',
            tokens: cm.context_window || match?.tokens || '32k tokens',
          }
        })
      : BUILT_IN_MODELS

  return (
    <form
      onSubmit={(e) => void handleAiSave(e)}
      className="card space-y-6 border border-slate-200 bg-white p-6 md:p-8 shadow-sm rounded-2xl transition-all"
    >
      <div
        onClick={() => setIsWritingOpen(!isWritingOpen)}
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4 cursor-pointer select-none"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-blue-100 text-blue-700">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Modelo de Redacción y Chat</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Modelos de lenguaje optimizados para redacción de historias de usuario, criterios de aceptación Gherkin y chat interactivo.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
          {!isWritingOpen && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
              Activo: <span className="font-mono text-[11px] text-[#002777] font-bold">{provider} • {model}</span>
            </span>
          )}
          <div
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
            title={isWritingOpen ? 'Plegar panel' : 'Desplegar panel'}
          >
            {isWritingOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </div>
        </div>
      </div>

      {isWritingOpen && (
        <>
          {/* Selector de Proveedor / Tipo de Modelo */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-800 block">
              Proveedor del Modelo de Inferencia
            </label>

            <select
              value={provider}
              onChange={(e) => {
                const newProv = e.target.value
                setProvider(newProv)
                if (newProv === 'builtin') {
                  setModel('qwen3.5:2b')
                } else if (newProv === 'ollama') {
                  if (ollamaModels.length > 0) {
                    setModel(ollamaModels[0])
                  } else {
                    setModel('gemma3:1b')
                  }
                  void fetchOllamaModels(undefined, false)
                } else if (newProv === 'groq') {
                  setModel('llama-3.3-70b-versatile')
                } else if (newProv === 'gemini') {
                  setModel('gemini-1.5-flash')
                } else if (newProv === 'openai') {
                  setModel('gpt-4o-mini')
                } else if (newProv === 'claude') {
                  setModel('claude-3-5-haiku-latest')
                }
              }}
              className="input-field text-sm font-medium text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2.5 px-3"
            >
              <option value="builtin">IA Integrada (Local, Sin API externa)</option>
              <option value="ollama">Ollama (Servidor Local / Remoto)</option>
              <option value="groq">Groq (API en la Nube)</option>
              <option value="gemini">Google Gemini (API en la Nube)</option>
              <option value="openai">OpenAI (API en la Nube)</option>
              <option value="claude">Claude (Anthropic API en la Nube)</option>
            </select>
          </div>

          {/* CASO 1: IA INTEGRADA LOCAL */}
          {provider === 'builtin' && (
            <div className="space-y-4 pt-2">
              <h4 className="text-sm font-bold text-slate-900">Modelos de IA Integrados (Locales)</h4>

              {pullStatusMsg ? (
                <div className="rounded-xl bg-blue-50 border border-blue-200 p-3 text-xs font-medium text-[#002777] flex items-center gap-2">
                  <RefreshCw className={`h-4 w-4 shrink-0 ${isPulling ? 'animate-spin text-[#004497]' : 'text-emerald-600'}`} />
                  <span>{pullStatusMsg}</span>
                </div>
              ) : null}

              <div className="space-y-3">
                {builtinModelsList.map((m) => {
                  const downloaded = isModelDownloaded(m.tag || m.id)
                  const isSelected = model === m.id || model === m.tag
                  const isCurrentlyPulling = isPulling && (pullingModelTag === m.tag || pullingModelTag === m.id)
                  const isDeleting = deletingModelTag === m.tag || deletingModelTag === m.id

                  return (
                    <div
                      key={m.id}
                      onClick={() => {
                        setModel(m.id)
                      }}
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
                          {downloaded ? (
                            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Descargado ({m.size})
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200">
                              No descargado ({m.size})
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
                          <span>Tamaño: {m.size}</span>
                          <span>•</span>
                          <span>Contexto / Tokens: {m.tokens}</span>
                        </p>
                      </div>

                      <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        {downloaded ? (
                          <>
                            {handleDeleteModel && (
                              <button
                                type="button"
                                disabled={isDeleting}
                                onClick={() => void handleDeleteModel(m.tag || m.id)}
                                title="Eliminar modelo para liberar espacio en disco"
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
                              onClick={() => setModel(m.id)}
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
                            <button
                              type="button"
                              disabled={isCurrentlyPulling}
                              onClick={() => void handlePullModel(m.tag || m.id)}
                              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-[#002777] bg-blue-50 hover:bg-blue-100 border border-blue-200 transition cursor-pointer disabled:opacity-50"
                            >
                              {isCurrentlyPulling ? (
                                <>
                                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />
                                  <span>Descargando…</span>
                                </>
                              ) : (
                                <>
                                  <Download className="h-3.5 w-3.5 text-[#002777]" />
                                  <span>Descargar ({m.size})</span>
                                </>
                              )}
                            </button>

                            <button
                              type="button"
                              onClick={() => setModel(m.id)}
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

          {/* CASO 2: PROVEEDOR OLLAMA */}
          {provider === 'ollama' && (
            <div className="space-y-5 pt-2">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-800 block">
                    Modelo de frontera
                  </label>
                  <select
                    value={
                      ollamaModels.includes(model) || OLLAMA_RECOMMENDED.some((m) => m.id === model)
                        ? model
                        : 'custom'
                    }
                    onChange={(e) => {
                      if (e.target.value === 'custom') {
                        setModel('')
                      } else {
                        setModel(e.target.value)
                      }
                    }}
                    className="input-field text-sm font-medium text-slate-900 border border-slate-300 rounded-xl"
                  >
                    {ollamaModels.length > 0 && (
                      <optgroup label="Modelos Instalados en Ollama">
                        {ollamaModels.map((m) => (
                          <option key={m} value={m}>
                            {m} (Instalado)
                          </option>
                        ))}
                      </optgroup>
                    )}
                    <optgroup label="Modelos Recomendados">
                      {OLLAMA_RECOMMENDED.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </optgroup>
                    <option value="custom">Otro Modelo (Personalizado)</option>
                  </select>
                </div>

                {!ollamaModels.includes(model) && !OLLAMA_RECOMMENDED.some((m) => m.id === model) && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-800 block">
                      Identificador de Modelo Personalizado
                    </label>
                    <input
                      type="text"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder="Ej. gemma3:1b, llama3.2, deepseek-r1:8b"
                      className="input-field font-mono text-xs border border-slate-300 rounded-xl"
                    />
                  </div>
                )}
              </div>

              {/* Endpoint Personalizado (Opcional) */}
              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setShowEndpointSection(!showEndpointSection)}
                  className="flex items-center justify-between w-full text-left cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-800">
                      Endpoint Personalizado (Opcional)
                    </span>
                    {ollamaOnline === true && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        En línea
                      </span>
                    )}
                    {ollamaOnline === false && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
                        Desconectado
                      </span>
                    )}
                  </div>
                  {showEndpointSection ? (
                    <ChevronUp className="h-4 w-4 text-slate-500" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-slate-500" />
                  )}
                </button>

                {showEndpointSection && (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-500">
                      Deja vacío para usar el valor por defecto o ingresa un endpoint personalizado (ej. http://localhost:11434)
                    </p>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={ollamaUrl}
                        onChange={(e) => setOllamaUrl(e.target.value)}
                        placeholder="http://localhost:11434"
                        className="input-field font-mono text-xs flex-1 border border-slate-300 rounded-xl py-2.5 px-3"
                      />
                      <button
                        type="button"
                        onClick={() => void fetchOllamaModels(undefined, true)}
                        disabled={fetchingModels}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-700 shadow-sm transition shrink-0 cursor-pointer"
                      >
                        <RotateCw className={`h-3.5 w-3.5 ${fetchingModels ? 'animate-spin' : ''}`} />
                        <span>Consultar Modelos</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Modelos de Ollama Disponibles */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-800 block">
                  Modelos de Ollama Disponibles
                </label>

                {ollamaModels.length === 0 ? (
                  <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-xs text-slate-600">
                    No se encontraron modelos. Descarga un modelo recomendado o haz clic en "Consultar Modelos" para cargar los modelos disponibles en tu servidor Ollama.
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
                    <p className="text-xs text-slate-500 mb-2">Modelos detectados en tu servidor Ollama:</p>
                    <div className="flex flex-wrap gap-2">
                      {ollamaModels.map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setModel(m)}
                          className={[
                            'rounded-lg px-3 py-1.5 text-xs font-mono transition cursor-pointer',
                            model === m
                              ? 'bg-slate-900 text-white font-bold shadow-sm'
                              : 'bg-slate-100 text-slate-700 hover:bg-slate-200',
                          ].join(' ')}
                        >
                          {m} {model === m ? '✓' : ''}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Botón de descarga rápida recomendada */}
                <div className="pt-2">
                  <button
                    type="button"
                    disabled={isPulling}
                    onClick={() => void handlePullModel('gemma3:1b')}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 py-2.5 px-4 text-xs font-semibold text-slate-800 shadow-sm transition cursor-pointer"
                  >
                    {isPulling && pullingModelTag === 'gemma3:1b' ? (
                      <RotateCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5" />
                    )}
                    <span>Descargar gemma3:1b (Recomendado)</span>
                  </button>
                </div>

                {pullStatusMsg ? (
                  <div className="rounded-xl bg-blue-50 border border-blue-200 p-3 text-xs font-medium text-[#002777] flex items-center gap-2">
                    <RefreshCw className={`h-4 w-4 shrink-0 ${isPulling ? 'animate-spin text-[#004497]' : 'text-emerald-600'}`} />
                    <span>{pullStatusMsg}</span>
                  </div>
                ) : null}
              </div>
            </div>
          )}

          {/* CASO 3: PROVEEDORES CLOUD (GROQ, GEMINI, OPENAI, CLAUDE) */}
          {['groq', 'gemini', 'openai', 'claude'].includes(provider) && (() => {
            const dropdownModels = catalogModels
              .filter((m) => m.provider === provider && m.task_type === 'chat_writing')
              .map((m) => ({ id: m.id, name: m.name }))

            const currentModelDetails = catalogModels.find(
              (m) => m.provider === provider && m.id === model,
            )

            return (
              <div className="space-y-4 pt-2">

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-800 block">
                      Modelo de frontera
                    </label>
                    <select
                      value={dropdownModels.some((m) => m.id === model) ? model : 'custom'}
                      onChange={(e) => {
                        if (e.target.value === 'custom') {
                          setModel('')
                        } else {
                          setModel(e.target.value)
                        }
                      }}
                      className="input-field text-sm font-medium text-slate-900 border border-slate-300 rounded-xl"
                    >
                      {dropdownModels.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                      <option value="custom">Otro Modelo (Personalizado)</option>
                    </select>
                  </div>

                  {!dropdownModels.some((m) => m.id === model) && (
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-slate-800 block">
                        Identificador de Modelo Personalizado
                      </label>
                      <input
                        type="text"
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                        placeholder="Ej. gpt-4o, llama-3.3-70b-versatile, gemini-1.5-flash"
                        className="input-field font-mono text-xs border border-slate-300 rounded-xl"
                      />
                    </div>
                  )}
                </div>

                {/* Resumen de Tarifas y Límites del Modelo Seleccionado */}
                {currentModelDetails && (
                  <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-3.5 space-y-2 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-900">{currentModelDetails.name}</span>
                        <code className="text-[11px] font-mono text-slate-600 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                          {currentModelDetails.id}
                        </code>
                      </div>
                      {currentModelDetails.is_free ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                          <Sparkles className="h-3 w-3" /> Gratuito (Free Tier)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-bold text-indigo-800">
                          De Pago
                        </span>
                      )}
                    </div>

                    <div className="grid gap-2 sm:grid-cols-3 text-[11px]">
                      <div>
                        <span className="text-slate-500 block flex items-center gap-1">
                          <Gauge className="h-3 w-3 text-amber-600" /> Límites de uso:
                        </span>
                        <strong className="text-slate-800">{currentModelDetails.rate_limits}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block flex items-center gap-1">
                          <Coins className="h-3 w-3 text-emerald-600" /> Costo tokens:
                        </span>
                        <strong className="text-slate-800">{currentModelDetails.pricing_label}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Ventana de contexto:</span>
                        <strong className="text-slate-800">{currentModelDetails.context_window}</strong>
                      </div>
                    </div>

                    {currentModelDetails.max_output_tokens && (
                      <div className="pt-2 border-t border-blue-100 flex items-center justify-between text-[11px]">
                        <span className="text-slate-500">Tope de salida por respuesta:</span>
                        <span className="font-semibold text-slate-700 bg-white px-2 py-0.5 rounded border border-slate-200">
                          {currentModelDetails.max_output_tokens.toLocaleString()} tokens
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* Campo API Key según proveedor */}
                {provider === 'groq' && (
                  <div className="space-y-2 rounded-xl bg-slate-50 p-4 border border-slate-200">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                        <Lock className="h-3.5 w-3.5" /> Clave de API de Groq
                      </label>
                      {ai?.groq_api_key_set ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                          <Check className="h-3 w-3" /> Clave guardada
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                          Sin clave configurada
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <input
                        type={showKey ? 'text' : 'password'}
                        value={groqKey}
                        onChange={(e) => setGroqKey(e.target.value)}
                        placeholder={ai?.groq_api_key_set ? '••••••••••••••••' : 'gsk_... (Ingresa tu clave de Groq)'}
                        className="input-field pr-10 font-mono text-xs border border-slate-300 rounded-xl"
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey(!showKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                      >
                        {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                )}

                {provider === 'gemini' && (
                  <div className="space-y-2 rounded-xl bg-slate-50 p-4 border border-slate-200">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                        <Lock className="h-3.5 w-3.5" /> Clave de API de Google Gemini (AI Studio)
                      </label>
                      {ai?.gemini_api_key_set ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                          <Check className="h-3 w-3" /> Clave guardada
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                          Sin clave configurada
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <input
                        type={showKey ? 'text' : 'password'}
                        value={geminiKey}
                        onChange={(e) => setGeminiKey(e.target.value)}
                        placeholder={
                          ai?.gemini_api_key_set
                            ? '••••••••••••••••'
                            : 'AIzaSy... (Ingresa tu clave de Google Gemini API)'
                        }
                        className="input-field pr-10 font-mono text-xs border border-slate-300 rounded-xl"
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey(!showKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                      >
                        {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Puedes generar una clave gratuita en{' '}
                      <a
                        href="https://aistudio.google.com/app/apikey"
                        target="_blank"
                        rel="noreferrer"
                        className="text-[#002777] font-semibold underline"
                      >
                        Google AI Studio
                      </a>{' '}
                      con generosos límites de uso sin costo.
                    </p>
                  </div>
                )}

                {provider === 'openai' && (
                  <div className="space-y-2 rounded-xl bg-slate-50 p-4 border border-slate-200">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                        <Lock className="h-3.5 w-3.5" /> Clave de API de OpenAI
                      </label>
                      {ai?.openai_api_key_set ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                          <Check className="h-3 w-3" /> Clave guardada
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                          Sin clave configurada
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <input
                        type={showKey ? 'text' : 'password'}
                        value={openaiKey}
                        onChange={(e) => setOpenaiKey(e.target.value)}
                        placeholder={ai?.openai_api_key_set ? '••••••••••••••••' : 'sk-proj-... (Ingresa tu clave de OpenAI)'}
                        className="input-field pr-10 font-mono text-xs border border-slate-300 rounded-xl"
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey(!showKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                      >
                        {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                )}

                {provider === 'claude' && (
                  <div className="space-y-2 rounded-xl bg-slate-50 p-4 border border-slate-200">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                        <Lock className="h-3.5 w-3.5" /> Clave de API de Anthropic Claude
                      </label>
                      {ai?.claude_api_key_set ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                          <Check className="h-3 w-3" /> Clave guardada
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                          Sin clave configurada
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <input
                        type={showKey ? 'text' : 'password'}
                        value={claudeKey}
                        onChange={(e) => setClaudeKey(e.target.value)}
                        placeholder={ai?.claude_api_key_set ? '••••••••••••••••' : 'sk-ant-... (Ingresa tu clave de Claude)'}
                        className="input-field pr-10 font-mono text-xs border border-slate-300 rounded-xl"
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey(!showKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                      >
                        {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })()}

          {/* Botones Probar Conexión y Guardar */}
          <div className="flex flex-wrap items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              disabled={testingConnection || savingAi}
              onClick={() => void handleTestConnection()}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium px-5 py-2.5 shadow-sm transition text-sm disabled:opacity-60 cursor-pointer"
            >
              {testingConnection ? <RefreshCw className="h-4 w-4 animate-spin text-blue-600" /> : <Zap className="h-4 w-4 text-amber-500" />}
              <span>{testingConnection ? 'Probando Conexión…' : 'Probar Conexión'}</span>
            </button>

            <button
              type="submit"
              disabled={savingAi || testingConnection}
              className="bg-[#002777] hover:bg-[#001f5f] text-white font-bold px-6 py-2.5 rounded-xl shadow-xs transition flex items-center gap-2 cursor-pointer text-sm disabled:opacity-50"
            >
              {savingAi ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              <span>Guardar Modelo de Redacción</span>
            </button>
          </div>
        </>
      )}
    </form>
  )
}
