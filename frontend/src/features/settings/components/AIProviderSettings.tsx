import { useEffect, useState, useMemo } from 'react'
import {
  Brain,
  Check,
  Cpu,
  Mic,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { api } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'
import type { ProviderCredentialInfo, ModelCatalogItem } from '../types'
import { ProviderCredentialCard } from './ProviderCredentialCard'

const SUPPORTED_BYOK_PROVIDERS = [
  { id: 'openai', label: 'OpenAI', description: 'Modelos GPT-4o, GPT-4o-mini y Whisper' },
  { id: 'anthropic', label: 'Anthropic (Claude)', description: 'Modelos Claude 3.5 Sonnet y Haiku' },
  { id: 'gemini', label: 'Google Gemini', description: 'Modelos Gemini 2.5 Pro y Flash' },
  { id: 'groq', label: 'Groq Cloud', description: 'Inferencia ultra rápida LLaMA 3.3 y Whisper' },
]

export const AIProviderSettings = () => {
  const { toast } = useToast()
  const [credentials, setCredentials] = useState<Record<string, ProviderCredentialInfo>>({})
  const [catalogModels, setCatalogModels] = useState<ModelCatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [savingPrefs, setSavingPrefs] = useState(false)

  // Local state for dropdown selectors
  const [inferenceProvider, setInferenceProvider] = useState<string>('builtin')
  const [inferenceModel, setInferenceModel] = useState<string>('Qwen2.5-1.5B-Instruct-q4f16_1-MLC')
  const [transcriptionProvider, setTranscriptionProvider] = useState<string>('groq')
  const [transcriptionModel, setTranscriptionModel] = useState<string>('whisper-large-v3')

  const loadData = async () => {
    setLoading(true)
    try {
      const [prefsData, credsList, catalogRes] = await Promise.all([
        api.getUserPreferences().catch(() => null),
        api.listProviderCredentials().catch(() => []),
        api.getModelCatalog(false).catch(() => ({ models: [] })),
      ])

      if (prefsData) {
        if (prefsData.inference_provider) setInferenceProvider(prefsData.inference_provider)
        if (prefsData.inference_model) setInferenceModel(prefsData.inference_model)
        if (prefsData.transcription_provider) setTranscriptionProvider(prefsData.transcription_provider)
        if (prefsData.transcription_model) setTranscriptionModel(prefsData.transcription_model)
      }

      const credsMap: Record<string, ProviderCredentialInfo> = {}
      for (const c of credsList) {
        credsMap[c.provider.toLowerCase()] = c
      }
      setCredentials(credsMap)

      setCatalogModels(catalogRes.models || [])
    } catch {
      toast.error('Error al cargar la configuración de proveedores de IA.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  // Filter models for current selected providers
  const availableInferenceModels = useMemo(() => {
    return catalogModels.filter(
      (m) => m.task_type === 'chat_writing' && (inferenceProvider === 'all' || m.provider === inferenceProvider)
    )
  }, [catalogModels, inferenceProvider])

  const availableTranscriptionModels = useMemo(() => {
    return catalogModels.filter(
      (m) => m.task_type === 'transcription' && (transcriptionProvider === 'all' || m.provider === transcriptionProvider)
    )
  }, [catalogModels, transcriptionProvider])

  const handleSavePreferences = async () => {
    setSavingPrefs(true)
    try {
      await api.updateUserPreferences({
        inference_provider: inferenceProvider,
        inference_model: inferenceModel,
        transcription_provider: transcriptionProvider,
        transcription_model: transcriptionModel,
      })
      toast.success('Preferencias personales de IA actualizadas.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar preferencias.')
    } finally {
      setSavingPrefs(false)
    }
  }

  const handleSaveCredential = async (provider: string, apiKey: string) => {
    try {
      const res = await api.setProviderCredential(provider, apiKey)
      setCredentials((prev) => ({ ...prev, [provider]: res }))
      toast.success(`API Key para ${provider.toUpperCase()} guardada de forma segura.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar la credencial.')
    }
  }

  const handleTestCredential = async (provider: string) => {
    try {
      const res = await api.validateProviderCredential(provider)
      if (res.ok) {
        toast.success(`Credencial de ${provider.toUpperCase()} validada con éxito.`)
      } else {
        toast.warning(`La credencial de ${provider.toUpperCase()} no pudo ser verificada.`)
      }
      // Re-fetch credentials list to get updated status
      const creds = await api.listProviderCredentials()
      const credsMap: Record<string, ProviderCredentialInfo> = {}
      for (const c of creds) {
        credsMap[c.provider.toLowerCase()] = c
      }
      setCredentials(credsMap)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al validar credencial.')
    }
  }

  const handleDeleteCredential = async (provider: string) => {
    try {
      await api.deleteProviderCredential(provider)
      setCredentials((prev) => {
        const copy = { ...prev }
        delete copy[provider]
        return copy
      })
      toast.success(`Credencial de ${provider.toUpperCase()} eliminada.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al eliminar credencial.')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8 text-slate-500 text-sm">
        <RefreshCw className="h-5 w-5 animate-spin mr-2" />
        <span>Cargando configuración de IA...</span>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Sección 1: Selección Activa de Modelos */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm space-y-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-50 text-[#002777]">
              <Cpu className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">Modelos de IA Seleccionados</h3>
              <p className="text-xs text-slate-500">
                Define independientemente tu motor de inferencia (chat/redacción) y tu motor de transcripción (voz a texto).
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void handleSavePreferences()}
            disabled={savingPrefs}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition flex items-center gap-1.5"
          >
            <Check className="h-4 w-4" />
            <span>{savingPrefs ? 'Guardando...' : 'Guardar selección'}</span>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Inferencia */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5 space-y-4">
            <div className="flex items-center gap-2 text-slate-900 font-bold text-sm">
              <Brain className="h-4 w-4 text-blue-600" />
              <span>Inferencia (Chat & Redacción)</span>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Proveedor de Inferencia
                </label>
                <select
                  value={inferenceProvider}
                  onChange={(e) => {
                    const p = e.target.value
                    setInferenceProvider(p)
                    // Pick sensible default model
                    const firstMatch = catalogModels.find((m) => m.provider === p && m.task_type === 'chat_writing')
                    if (firstMatch) setInferenceModel(firstMatch.id || firstMatch.raw_id)
                  }}
                  className="w-full px-3 py-2 text-xs font-medium text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                >
                  <option value="builtin">Built-in (Navegador WebLLM)</option>
                  <option value="groq">Groq Cloud (BYOK)</option>
                  <option value="gemini">Google Gemini (BYOK)</option>
                  <option value="openai">OpenAI (BYOK)</option>
                  <option value="claude">Anthropic Claude (BYOK)</option>
                  <option value="ollama">Ollama Local</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Modelo de Inferencia
                </label>
                {availableInferenceModels.length > 0 ? (
                  <select
                    value={inferenceModel}
                    onChange={(e) => setInferenceModel(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-medium text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100 font-mono"
                  >
                    {availableInferenceModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name || m.id} ({m.context_window || 'Context'})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={inferenceModel}
                    onChange={(e) => setInferenceModel(e.target.value)}
                    placeholder="Identificador del modelo"
                    className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                )}
              </div>
            </div>
          </div>

          {/* Transcripción */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5 space-y-4">
            <div className="flex items-center gap-2 text-slate-900 font-bold text-sm">
              <Mic className="h-4 w-4 text-emerald-600" />
              <span>Transcripción & Audio (Whisper)</span>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Proveedor de Transcripción
                </label>
                <select
                  value={transcriptionProvider}
                  onChange={(e) => {
                    const p = e.target.value
                    setTranscriptionProvider(p)
                    const firstMatch = catalogModels.find((m) => m.provider === p && m.task_type === 'transcription')
                    if (firstMatch) setTranscriptionModel(firstMatch.id || firstMatch.raw_id)
                  }}
                  className="w-full px-3 py-2 text-xs font-medium text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                >
                  <option value="groq">Groq Cloud (Whisper Rápido BYOK)</option>
                  <option value="openai">OpenAI (Whisper-1 BYOK)</option>
                  <option value="local">Whisper Local (En equipo)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Modelo de Transcripción
                </label>
                {availableTranscriptionModels.length > 0 ? (
                  <select
                    value={transcriptionModel}
                    onChange={(e) => setTranscriptionModel(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-medium text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100 font-mono"
                  >
                    {availableTranscriptionModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name || m.id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={transcriptionModel}
                    onChange={(e) => setTranscriptionModel(e.target.value)}
                    placeholder="whisper-large-v3, whisper-1, base..."
                    className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sección 2: Gestión de Credenciales BYOK */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm space-y-6">
        <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
          <div className="p-2 rounded-xl bg-amber-50 text-amber-700">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Credenciales Personales BYOK (Bring Your Own Key)</h3>
            <p className="text-xs text-slate-500">
              Guarda tus claves API personales cifradas en reposo con AES-256-GCM. Ninguna clave se muestra ni se envía en texto plano.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SUPPORTED_BYOK_PROVIDERS.map((prov) => {
            const cred = credentials[prov.id] || (prov.id === 'anthropic' ? credentials['claude'] : undefined)
            return (
              <ProviderCredentialCard
                key={prov.id}
                provider={prov.id}
                label={prov.label}
                description={prov.description}
                credential={cred}
                onSave={(key) => handleSaveCredential(prov.id, key)}
                onTest={() => handleTestCredential(prov.id)}
                onDelete={() => handleDeleteCredential(prov.id)}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}
