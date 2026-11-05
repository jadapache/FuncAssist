import type { FormEvent } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { api, type AISettings, type ModelCatalogItem } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'
import { normalizeOllamaUrl, validateAiSettingsPayload } from '../validators/settingsValidation'
import { inferenceService } from '../../ai/services/InferenceService'
import { DEFAULT_BROWSER_ASR_MODEL, DEFAULT_WEBLLM_MODEL, setDynamicClientCatalog } from '../../ai/catalogs/clientCatalog'

let webLLMProviderPromise: Promise<Awaited<typeof import('../../ai/providers/WebLLMProvider')>['webLLMProvider']> | null = null

async function getWebLLMProvider() {
  if (!webLLMProviderPromise) {
    webLLMProviderPromise = import('../../ai/providers/WebLLMProvider').then((m) => m.webLLMProvider)
  }
  return webLLMProviderPromise
}

export function useAiSettingsManager() {
  const { toast } = useToast()

  const [ai, setAi] = useState<AISettings | null>(null)
  const [loadingAi, setLoadingAi] = useState(true)

  const [provider, setProvider] = useState<string>('local')
  const [model, setModel] = useState<string>(DEFAULT_WEBLLM_MODEL)

  const [isWritingOpen, setIsWritingOpen] = useState(true)
  const [isVoiceAudioOpen, setIsVoiceAudioOpen] = useState(true)
  const [showEndpointSection, setShowEndpointSection] = useState(true)

  const [catalogModels, setCatalogModels] = useState<ModelCatalogItem[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)

  const [voiceAudioProvider, setVoiceAudioProvider] = useState<string>('local')
  const [voiceAudioModel, setVoiceAudioModel] = useState<string>(DEFAULT_BROWSER_ASR_MODEL)
  const [transcriptionGroqKey, setTranscriptionGroqKey] = useState('')
  const [transcriptionOpenaiKey, setTranscriptionOpenaiKey] = useState('')
  const [showTranscriptionKey, setShowTranscriptionKey] = useState(false)

  const [groqKey, setGroqKey] = useState('')
  const [geminiKey, setGeminiKey] = useState('')
  const [openaiKey, setOpenaiKey] = useState('')
  const [claudeKey, setClaudeKey] = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('')
  const [showKey, setShowKey] = useState(false)

  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [fetchingModels, setFetchingModels] = useState(false)

  const [savingAi, setSavingAi] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [configuredCreds, setConfiguredCreds] = useState<string[]>([])

  const loadDynamicCatalog = useCallback(async (forceRefresh = false) => {
    try {
      const res = await api.getModelCatalog(forceRefresh)
      setCatalogError(res.error || null)
      setCatalogModels(res.models || [])
      if (res.models) {
        setDynamicClientCatalog(res.models)
      }
    } catch {
      setCatalogError('Error de conexión al cargar catálogo externo.')
      setCatalogModels([])
    }
  }, [])

  const fetchOllamaModels = useCallback(async (url?: string, isUserAction = false) => {
    setFetchingModels(true)
    const target = normalizeOllamaUrl(url !== undefined ? url : ollamaUrl)
    try {
      const res = await api.listOllamaModels(target)
      setOllamaOnline(res.online)
      setOllamaModels(res.models || [])
      if (!res.online && isUserAction) {
        toast.error(`No se pudo conectar con el servidor Ollama remoto en "${target}".`)
      } else if (res.online && isUserAction) {
        toast.success(`Conexión exitosa con servidor Ollama remoto (${res.models?.length || 0} modelos disponibles).`)
      }
    } catch (err) {
      setOllamaOnline(false)
      setOllamaModels([])
      if (isUserAction) {
        toast.error(`Error de conexión con Ollama remoto: ${err instanceof Error ? err.message : 'Error desconocido'}`)
      }
    } finally {
      setFetchingModels(false)
    }
  }, [ollamaUrl, toast])

  useEffect(() => {
    let isMounted = true
    const load = async () => {
      setLoadingAi(true)
      try {
        await loadDynamicCatalog(false)
        const [settings, userPrefs, credsList] = await Promise.all([
          api.getAiSettings(),
          api.getUserPreferences().catch(() => null),
          api.listProviderCredentials().catch(() => []),
        ])
        if (!isMounted) return
        setAi(settings)
        setConfiguredCreds(credsList.map((c) => c.provider.toLowerCase()))
        const rawProv = userPrefs?.inference_provider || settings.provider || 'local'
        const effectiveProv = rawProv === 'builtin' ? 'local' : rawProv === 'ollama' ? 'ollama_remote' : rawProv
        setProvider(effectiveProv)

        const activeModel = userPrefs?.inference_model || settings.model
        setModel(activeModel || (effectiveProv === 'local' ? DEFAULT_WEBLLM_MODEL : 'llama-3.3-70b-versatile'))

        const rawTransProv = userPrefs?.transcription_provider || settings.transcription_provider || 'local'
        const effectiveTransProv = rawTransProv === 'builtin' || rawTransProv === 'browser_asr' ? 'local' : rawTransProv
        setVoiceAudioProvider(effectiveTransProv)

        const savedTransModel = userPrefs?.transcription_model || settings.transcription_model
        setVoiceAudioModel(savedTransModel || (effectiveTransProv === 'local' ? DEFAULT_BROWSER_ASR_MODEL : 'whisper-large-v3'))

        if (settings.ollama_base_url) {
          setOllamaUrl(settings.ollama_base_url)
          void fetchOllamaModels(settings.ollama_base_url, false)
        }
      } catch (err) {
        if (isMounted) {
          toast.error(err instanceof Error ? err.message : 'Error al cargar configuración.')
        }
      } finally {
        if (isMounted) {
          setLoadingAi(false)
        }
      }
    }
    void load()

    return () => {
      isMounted = false
    }
  }, [fetchOllamaModels, loadDynamicCatalog, toast])

  const checkIsKeyConfigured = (p: string): boolean => {
    if (configuredCreds.includes(p)) return true
    if (p === 'groq') return Boolean(ai?.groq_api_key_set)
    if (p === 'gemini') return Boolean(ai?.gemini_api_key_set)
    if (p === 'openai') return Boolean(ai?.openai_api_key_set)
    if (p === 'claude') return Boolean(ai?.claude_api_key_set)
    return true
  }

  const handleAiSave = async (event?: FormEvent) => {
    if (event) event.preventDefault()

    const validation = validateAiSettingsPayload({
      provider,
      model,
      ollamaUrl,
      groqKey,
      geminiKey,
      openaiKey,
      claudeKey,
      isKeyConfigured: checkIsKeyConfigured(provider),
    })

    if (!validation.isValid) {
      toast.error(validation.error || 'Verifica los campos ingresados.')
      return
    }

    setSavingAi(true)
    const payload: Record<string, string> = {
      provider,
      model: model.trim(),
      inference_provider: provider,
      inference_model: model.trim(),
      ollama_base_url: normalizeOllamaUrl(ollamaUrl),
    }

    if (groqKey.trim()) payload.groq_api_key = groqKey.trim()
    if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim()
    if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim()
    if (claudeKey.trim()) payload.claude_api_key = claudeKey.trim()

    try {
      const updated = await api.updateAiSettings(payload)
      setAi(updated)
      inferenceService.setAiSettings(updated)
      await api.updateUserPreferences({
        inference_provider: provider,
        inference_model: model.trim(),
      }).catch(() => null)
      setGroqKey('')
      setGeminiKey('')
      setOpenaiKey('')
      setClaudeKey('')
      toast.success('Configuración guardada exitosamente.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar la configuración.')
    } finally {
      setSavingAi(false)
    }
  }

  const handleTestConnection = async () => {
    const validation = validateAiSettingsPayload({
      provider,
      model,
      ollamaUrl,
      groqKey,
      geminiKey,
      openaiKey,
      claudeKey,
      isKeyConfigured: checkIsKeyConfigured(provider),
    })

    if (!validation.isValid) {
      toast.error(validation.error || 'Verifica los campos ingresados.')
      return
    }

    setTestingConnection(true)
    if (provider === 'local' || provider === 'builtin') {
      try {
        const webllm = await getWebLLMProvider()
        const isCached = await webllm.isModelCached(model)
        if (!isCached) {
          toast.error(`El modelo ${model} no está descargado en la caché del navegador.`)
          return
        }
        await webllm.initModel(model)
        const answer = await webllm.complete([
          { role: 'user', content: 'Responde únicamente con OK.' },
        ], { maxTokens: 10 })
        toast.success(`Prueba exitosa con WebLLM (${model}): ${answer}`)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error al probar modelo en navegador.')
      } finally {
        setTestingConnection(false)
      }
      return
    }

    const payload: Record<string, string> = {
      provider,
      model: model.trim(),
      ollama_base_url: normalizeOllamaUrl(ollamaUrl),
    }

    if (groqKey.trim()) payload.groq_api_key = groqKey.trim()
    if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim()
    if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim()
    if (claudeKey.trim()) payload.claude_api_key = claudeKey.trim()

    try {
      const res = await api.testAiConnection(payload)
      if (res.ok || res.status === 'ok') {
        toast.success(res.message || 'Prueba de conexión exitosa.')
      } else {
        toast.error(res.message || 'La prueba de conexión ha fallado.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al probar conexión.')
    } finally {
      setTestingConnection(false)
    }
  }

  const handleVoiceAudioSave = async (event?: FormEvent) => {
    if (event) event.preventDefault()
    setSavingAi(true)

    const payload: Record<string, string> = {
      transcription_provider: voiceAudioProvider,
      transcription_model: voiceAudioModel.trim(),
    }

    if (transcriptionGroqKey.trim()) {
      payload.transcription_groq_api_key = transcriptionGroqKey.trim()
    }
    if (transcriptionOpenaiKey.trim()) {
      payload.transcription_openai_api_key = transcriptionOpenaiKey.trim()
    }

    try {
      const updated = await api.updateAiSettings(payload)
      setAi(updated)
      await api.updateUserPreferences({
        transcription_provider: voiceAudioProvider,
        transcription_model: voiceAudioModel.trim(),
      }).catch(() => null)
      setTranscriptionGroqKey('')
      setTranscriptionOpenaiKey('')
      toast.success('Configuración de transcripción guardada.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar configuración.')
    } finally {
      setSavingAi(false)
    }
  }

  return {
    ai,
    loadingAi,
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
    catalogModels,
    catalogError,
    loadDynamicCatalog,
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
    voiceAudioProvider,
    setVoiceAudioProvider,
    voiceAudioModel,
    setVoiceAudioModel,
    transcriptionGroqKey,
    setTranscriptionGroqKey,
    transcriptionOpenaiKey,
    setTranscriptionOpenaiKey,
    showTranscriptionKey,
    setShowTranscriptionKey,
    isVoiceAudioOpen,
    setIsVoiceAudioOpen,
    handleVoiceAudioSave,
  }
}
