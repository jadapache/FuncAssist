import type { FormEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type AISettings, type LocalBuiltinModelInfo, type LocalWhisperModelInfo, type ModelCatalogItem } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'
import { useBackgroundJobs, type BackgroundJobItem } from '../../../context/BackgroundJobContext'
import { normalizeOllamaUrl, validateAiSettingsPayload } from '../validators/settingsValidation'

export function useAiSettingsManager() {
  const { toast } = useToast()
  const { registerDownloadJob } = useBackgroundJobs()

  const [ai, setAi] = useState<AISettings | null>(null)
  const [loadingAi, setLoadingAi] = useState(true)

  // Provider state: 'builtin' | 'ollama' | 'groq' | 'gemini' | 'openai' | 'claude'
  const [provider, setProvider] = useState<string>('builtin')
  const [model, setModel] = useState<string>('qwen2.5:3b')

  // Collapsible panels
  const [isWritingOpen, setIsWritingOpen] = useState(true)
  const [isVoiceAudioOpen, setIsVoiceAudioOpen] = useState(true)
  const [showEndpointSection, setShowEndpointSection] = useState(true)

  // Dynamic models catalog
  const [catalogModels, setCatalogModels] = useState<ModelCatalogItem[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)

  // Voice & Transcription unified state
  const [voiceAudioProvider, setVoiceAudioProvider] = useState<string>('groq')
  const [voiceAudioModel, setVoiceAudioModel] = useState<string>('whisper-large-v3')
  const [transcriptionGroqKey, setTranscriptionGroqKey] = useState('')
  const [transcriptionOpenaiKey, setTranscriptionOpenaiKey] = useState('')
  const [showTranscriptionKey, setShowTranscriptionKey] = useState(false)

  // Local Whisper models & download state
  const [localWhisperModels, setLocalWhisperModels] = useState<LocalWhisperModelInfo[]>([])
  const [downloadingWhisperId, setDownloadingWhisperId] = useState<string | null>(null)
  const [deletingWhisperId, setDeletingWhisperId] = useState<string | null>(null)
  const [fetchingWhisperModels, setFetchingWhisperModels] = useState(false)

  // Local Built-in GGUF models & download state (standalone without Ollama)
  const [localBuiltinModels, setLocalBuiltinModels] = useState<LocalBuiltinModelInfo[]>([])
  const [downloadingBuiltinId, setDownloadingBuiltinId] = useState<string | null>(null)
  const [deletingBuiltinId, setDeletingBuiltinId] = useState<string | null>(null)
  const [fetchingBuiltinModels, setFetchingBuiltinModels] = useState(false)
  const [downloadTasks, setDownloadTasks] = useState<Record<string, BackgroundJobItem>>({})
  const downloadPollTimerRef = useRef<number | null>(null)


  // API Keys & credentials
  const [groqKey, setGroqKey] = useState('')
  const [geminiKey, setGeminiKey] = useState('')
  const [openaiKey, setOpenaiKey] = useState('')
  const [claudeKey, setClaudeKey] = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('')
  const [showKey, setShowKey] = useState(false)

  // Local Ollama models & pull state
  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [isPulling, setIsPulling] = useState(false)
  const [pullingModelTag, setPullingModelTag] = useState<string | null>(null)
  const [deletingModelTag, setDeletingModelTag] = useState<string | null>(null)
  const [pullStatusMsg, setPullStatusMsg] = useState<string | null>(null)
  const [fetchingModels, setFetchingModels] = useState(false)

  // Feedback states
  const [savingAi, setSavingAi] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)

  const loadDynamicCatalog = useCallback(async (forceRefresh = false) => {
    try {
      const res = await api.getModelCatalog(forceRefresh)
      if (res.error) {
        setCatalogError(res.error)
      } else {
        setCatalogError(null)
      }
      setCatalogModels(res.models || [])
    } catch (e) {
      console.error('Error al cargar catálogo de modelos:', e)
      setCatalogError('Error de conexión, no se pudo obtener los modelos')
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
      if (!res.online) {
        if (isUserAction) {
          toast.error(`No se pudo conectar con el servidor Ollama en "${target}". Asegúrate de que Ollama esté ejecutándose en tu equipo o verifica la dirección del endpoint.`)
        }
      } else {
        if (isUserAction) {
          toast.success(`Conexión exitosa: Se encontraron ${res.models?.length || 0} modelo(s) en tu servidor Ollama.`)
        }
      }
    } catch (err) {
      setOllamaOnline(false)
      setOllamaModels([])
      if (isUserAction) {
        toast.error(`Error al consultar modelos en Ollama (${target}): ${err instanceof Error ? err.message : 'No se pudo conectar con el servidor'}`)
      }
    } finally {
      setFetchingModels(false)
    }
  }, [ollamaUrl, toast])

  const fetchLocalWhisperModels = useCallback(async () => {
    setFetchingWhisperModels(true)
    try {
      const res = await api.listWhisperModels()
      if (res.ok && res.models) {
        setLocalWhisperModels(res.models)
      }
    } catch (e) {
      console.error('Error fetching local whisper models:', e)
    } finally {
      setFetchingWhisperModels(false)
    }
  }, [])

  const fetchLocalBuiltinModels = useCallback(async () => {
    setFetchingBuiltinModels(true)
    try {
      const res = await api.listBuiltinModels()
      if (res.ok && res.models) {
        setLocalBuiltinModels(res.models)
      }
    } catch (e) {
      console.error('Error fetching local builtin models:', e)
    } finally {
      setFetchingBuiltinModels(false)
    }
  }, [])

  useEffect(() => {
    let isMounted = true
    const load = async () => {
      setLoadingAi(true)
      try {
        await loadDynamicCatalog(false)
        const settings = await api.getAiSettings()
        if (!isMounted) return
        setAi(settings)

        const isFirstTimeSetup = !settings.provider && !settings.transcription_provider

        const prov = settings.provider || 'builtin'
        setProvider(prov)

        if (settings.model) {
          setModel(settings.model)
        } else if (isFirstTimeSetup) {
          if (prov === 'groq') setModel('llama-3.3-70b-versatile')
          else if (prov === 'builtin') setModel('qwen3.5:2b')
          else if (prov === 'gemini') setModel('gemini-1.5-flash')
          else if (prov === 'openai') setModel('gpt-4o-mini')
          else if (prov === 'claude') setModel('claude-3-5-haiku-latest')
          else setModel('qwen3.5:2b')
        } else {
          // Provider exists but model is unset, assign sensible default for that provider
          if (prov === 'groq') setModel('llama-3.3-70b-versatile')
          else if (prov === 'builtin') setModel('qwen3.5:2b')
          else if (prov === 'gemini') setModel('gemini-1.5-flash')
          else if (prov === 'openai') setModel('gpt-4o-mini')
          else if (prov === 'claude') setModel('claude-3-5-haiku-latest')
        }

        if (settings.transcription_provider) {
          const savedProvider = settings.transcription_provider
          setVoiceAudioProvider(savedProvider)

          const savedModel = settings.transcription_model
          if (savedModel) {
            setVoiceAudioModel(savedModel)
          } else {
            const defaultTransModel =
              savedProvider === 'groq'
                ? 'whisper-large-v3'
                : savedProvider === 'openai'
                ? 'whisper-1'
                : 'base'
            setVoiceAudioModel(defaultTransModel)
          }
        } else if (isFirstTimeSetup) {
          setVoiceAudioProvider('groq')
          setVoiceAudioModel('whisper-large-v3')
        }

        if (
          settings.ollama_base_url &&
          settings.ollama_base_url !== 'http://localhost:11434' &&
          settings.ollama_base_url !== 'http://127.0.0.1:11434'
        ) {
          setOllamaUrl(settings.ollama_base_url)
        } else {
          setOllamaUrl('')
        }

        // Fetch local Ollama, Whisper and Built-in models silently in background
        void fetchOllamaModels(settings.ollama_base_url || 'http://localhost:11434', false)
        void fetchLocalWhisperModels()
        void fetchLocalBuiltinModels()
      } catch (err) {
        if (isMounted) {
          toast.error(err instanceof Error ? err.message : 'Error al cargar la configuración del sistema')
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
  }, [fetchLocalBuiltinModels, fetchLocalWhisperModels, fetchOllamaModels, loadDynamicCatalog, toast])

  const handleDownloadWhisperModel = async (modelId: string) => {
    const cleanId = modelId.replace('whisper-', '').trim()
    setDownloadingWhisperId(cleanId)
    registerDownloadJob(cleanId, `Descargando Whisper ${cleanId.toUpperCase()}`)
    try {
      toast.info(`Iniciando descarga de Whisper ${cleanId}... Esto puede demorar según tu conexión.`)
      const res = await api.downloadWhisperModel(cleanId)
      if (res.ok) {
        toast.success(res.message || `Modelo Whisper ${cleanId} descargado correctamente.`)
        await fetchLocalWhisperModels()
        await loadDynamicCatalog(true)
      }
    } catch (err) {
      const isCancelled = err instanceof Error && err.message.toLowerCase().includes('cancel')
      if (!isCancelled) {
        toast.error(err instanceof Error ? err.message : `Error descargando modelo ${cleanId}`)
      }
    } finally {
      setDownloadingWhisperId(null)
    }
  }

  const handleDeleteWhisperModel = async (modelId: string) => {
    setDeletingWhisperId(modelId)
    try {
      const res = await api.deleteWhisperModel(modelId)
      if (res.ok) {
        toast.success(res.message || `Modelo Whisper ${modelId} eliminado del disco.`)
        await fetchLocalWhisperModels()
        await loadDynamicCatalog(true)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Error al eliminar modelo ${modelId}`)
    } finally {
      setDeletingWhisperId(null)
    }
  }

  const handleCancelBuiltinDownload = useCallback(async (modelId: string) => {
    try {
      await api.cancelBuiltinModelDownload(modelId)
      toast.info(`Cancelando descarga del modelo ${modelId}...`)
      setDownloadTasks((prev) => {
        if (!prev[modelId]) return prev
        return {
          ...prev,
          [modelId]: {
            ...prev[modelId],
            status: 'cancelled',
            stageText: 'Descarga cancelada por el usuario',
          },
        }
      })
      setDownloadingBuiltinId(null)
      void fetchLocalBuiltinModels()
    } catch (e) {
      console.warn(`Error cancelling download for ${modelId}:`, e)
    }
  }, [fetchLocalBuiltinModels, toast])

  const handleDismissDownloadTask = useCallback((taskId: string) => {
    setDownloadTasks((prev) => {
      const copy = { ...prev }
      delete copy[taskId]
      return copy
    })
  }, [])

  // Poll active download tasks whenever downloadingBuiltinId is active
  useEffect(() => {
    if (!downloadingBuiltinId) {
      if (downloadPollTimerRef.current) {
        clearInterval(downloadPollTimerRef.current)
        downloadPollTimerRef.current = null
      }
      return
    }

    const poll = async () => {
      try {
        const res = await api.getBuiltinDownloadTasks()
        if (res.ok && Array.isArray(res.tasks)) {
          setDownloadTasks((prev) => {
            const next = { ...prev }
            for (const t of res.tasks) {
              next[t.id] = {
                id: t.id,
                type: 'download',
                title: t.title,
                progress: t.progress,
                status: (t.status === 'downloading' ? 'uploading' : t.status) as any,
                stageText: t.stageText || 'Descargando modelo GGUF...',
                speedOrSize: t.speedOrSize,
                eta: t.eta,
                onCancel: () => void handleCancelBuiltinDownload(t.id),
                onDismiss: () => handleDismissDownloadTask(t.id),
              }
            }
            return next
          })
        }
      } catch {
        // ignore polling errors
      }
    }

    downloadPollTimerRef.current = window.setInterval(() => {
      void poll()
    }, 600)
    void poll()

    return () => {
      if (downloadPollTimerRef.current) {
        clearInterval(downloadPollTimerRef.current)
        downloadPollTimerRef.current = null
      }
    }
  }, [downloadingBuiltinId, handleCancelBuiltinDownload, handleDismissDownloadTask])

  const handleDownloadBuiltinModel = async (modelId: string) => {
    setDownloadingBuiltinId(modelId)
    // Register in global BackgroundJobContext so it floats across all app views
    registerDownloadJob(modelId, `Descargando ${modelId}`)
    // Register initial task for immediate feedback in local state
    setDownloadTasks((prev) => ({
      ...prev,
      [modelId]: {
        id: modelId,
        type: 'download',
        title: `Descargando ${modelId}`,
        progress: 1,
        status: 'uploading',
        stageText: 'Conectando con el repositorio...',
        speedOrSize: 'Iniciando...',
        onCancel: () => void handleCancelBuiltinDownload(modelId),
        onDismiss: () => handleDismissDownloadTask(modelId),
      },
    }))

    try {
      const res = await api.downloadBuiltinModel(modelId)
      if (res.ok) {
        toast.success(res.message || `Modelo ${modelId} descargado correctamente en tu disco.`)
        setDownloadTasks((prev) => ({
          ...prev,
          [modelId]: {
            ...(prev[modelId] || { id: modelId, title: modelId, type: 'download' }),
            progress: 100,
            status: 'complete',
            stageText: 'Descarga completada con éxito',
            speedOrSize: 'Listo',
            onDismiss: () => handleDismissDownloadTask(modelId),
          },
        }))
        await fetchLocalBuiltinModels()
        await loadDynamicCatalog(true)
      } else {
        toast.error(res.message || `Error al descargar modelo ${modelId}`)
        setDownloadTasks((prev) => ({
          ...prev,
          [modelId]: {
            ...(prev[modelId] || { id: modelId, title: modelId, type: 'download' }),
            progress: 0,
            status: 'failed',
            stageText: res.message || 'Error en descarga',
            onDismiss: () => handleDismissDownloadTask(modelId),
          },
        }))
      }
    } catch (err) {
      const isCancelled = err instanceof Error && err.message.toLowerCase().includes('cancel')
      if (!isCancelled) {
        toast.error(err instanceof Error ? err.message : `Error descargando modelo ${modelId}`)
      }
      setDownloadTasks((prev) => ({
        ...prev,
        [modelId]: {
          ...(prev[modelId] || { id: modelId, title: modelId, type: 'download' }),
          progress: 0,
          status: isCancelled ? 'cancelled' : 'failed',
          stageText: isCancelled ? 'Descarga cancelada' : (err instanceof Error ? err.message : 'Error en descarga'),
          onDismiss: () => handleDismissDownloadTask(modelId),
        },
      }))
    } finally {
      setDownloadingBuiltinId(null)
    }
  }


  const handleDeleteBuiltinModel = async (modelId: string) => {
    setDeletingBuiltinId(modelId)
    try {
      const res = await api.deleteBuiltinModel(modelId)
      if (res.ok) {
        toast.success(res.message || `Modelo ${modelId} eliminado del disco.`)
        await fetchLocalBuiltinModels()
        await loadDynamicCatalog(true)
      } else {
        toast.error(res.message || `Error al eliminar modelo ${modelId}`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Error al eliminar modelo ${modelId}`)
    } finally {
      setDeletingBuiltinId(null)
    }
  }

  const handlePullModel = async (targetModelTag: string) => {
    setIsPulling(true)
    setPullingModelTag(targetModelTag)
    setPullStatusMsg(`Descargando "${targetModelTag}" desde el registro de Ollama…`)

    const effectiveTargetUrl = normalizeOllamaUrl(ollamaUrl)

    try {
      await api.pullOllamaModel(targetModelTag, effectiveTargetUrl)
      const successMsg = `¡Modelo "${targetModelTag}" descargado con éxito!`
      setPullStatusMsg(successMsg)
      toast.success(successMsg)
      setModel(targetModelTag)
      void fetchOllamaModels(effectiveTargetUrl, false)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : `Error al descargar el modelo ${targetModelTag}`
      toast.error(errMsg)
      setPullStatusMsg(null)
    } finally {
      setIsPulling(false)
      setPullingModelTag(null)
    }
  }

  const handleDeleteModel = async (targetModelTag: string) => {
    setDeletingModelTag(targetModelTag)
    const effectiveTargetUrl = normalizeOllamaUrl(ollamaUrl)

    try {
      await api.deleteOllamaModel(targetModelTag, effectiveTargetUrl)
      toast.success(`Modelo "${targetModelTag}" eliminado de Ollama correctamente.`)
      void fetchOllamaModels(effectiveTargetUrl, false)
      await loadDynamicCatalog(true)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : `Error al eliminar el modelo ${targetModelTag}`
      toast.error(errMsg)
    } finally {
      setDeletingModelTag(null)
    }
  }

  const isModelDownloaded = (modelTag: string) => {
    return ollamaModels.some((m) => m === modelTag || m.startsWith(`${modelTag}:`))
  }

  const checkIsKeyConfigured = (p: string) => {
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
      inference_provider: provider,
      inference_model: model.trim(),
      ollama_base_url: normalizeOllamaUrl(ollamaUrl),
      transcription_provider: voiceAudioProvider,
      transcription_model: voiceAudioModel.trim(),
    }

    if (groqKey.trim()) payload.groq_api_key = groqKey.trim()
    if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim()
    if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim()
    if (claudeKey.trim()) payload.claude_api_key = claudeKey.trim()

    try {
      const updated = await api.updateAiSettings(payload)
      setAi(updated)
      setGroqKey('')
      setGeminiKey('')
      setOpenaiKey('')
      setClaudeKey('')
      toast.success('Configuración del modelo de redacción y chat guardada exitosamente.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar la configuración de IA')
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
        toast.success(res.message || 'Prueba de conexión exitosa con el modelo de IA.')
      } else {
        toast.error(res.message || 'La prueba de conexión con el modelo ha fallado.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al realizar la prueba de conexión con el modelo.')
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
      setTranscriptionGroqKey('')
      setTranscriptionOpenaiKey('')
      toast.success('Configuración del motor de transcripción y voz guardada exitosamente.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar el modelo de voz y transcripción')
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
    isVoiceAudioOpen,
    setIsVoiceAudioOpen,
    showEndpointSection,
    setShowEndpointSection,
    catalogModels,
    catalogError,
    loadDynamicCatalog,
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
    groqKey,
    setGroqKey,
    geminiKey,
    setGeminiKey,
    openaiKey,
    setOpenaiKey,
    claudeKey,
    setClaudeKey,
    ollamaUrl,
    setOllamaUrl,
    showKey,
    setShowKey,
    ollamaOnline,
    ollamaModels,
    isPulling,
    pullingModelTag,
    deletingModelTag,
    pullStatusMsg,
    fetchingModels,
    fetchOllamaModels,
    handlePullModel,
    handleDeleteModel,
    isModelDownloaded,
    localWhisperModels,
    downloadingWhisperId,
    deletingWhisperId,
    fetchingWhisperModels,
    fetchLocalWhisperModels,
    handleDownloadWhisperModel,
    handleDeleteWhisperModel,
    localBuiltinModels,
    downloadingBuiltinId,
    deletingBuiltinId,
    fetchingBuiltinModels,
    fetchLocalBuiltinModels,
    handleDownloadBuiltinModel,
    handleDeleteBuiltinModel,
    handleCancelBuiltinDownload,
    handleDismissDownloadTask,
    downloadTasks,
    savingAi,
    testingConnection,
    handleAiSave,
    handleTestConnection,
    handleVoiceAudioSave,
  }
}

