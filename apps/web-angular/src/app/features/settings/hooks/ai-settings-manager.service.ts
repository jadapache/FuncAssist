import { DestroyRef, Injectable, inject, signal } from '@angular/core'
import { api, type AISettings, type ModelCatalogItem } from '../../../api/client'
import { ToastService } from '../../../core/notifications/toast.service'
import { normalizeOllamaUrl, validateAiSettingsPayload } from '../validators/settingsValidation'
import { inferenceService } from '../../ai/services/InferenceService'
import { DEFAULT_BROWSER_ASR_MODEL, DEFAULT_WEBLLM_MODEL, setDynamicClientCatalog } from '../../ai/catalogs/clientCatalog'

let webLLMProviderPromise: Promise<Awaited<typeof import('../../ai/providers/WebLLMProvider')>['webLLMProvider']> | null =
  null

async function getWebLLMProvider() {
  if (!webLLMProviderPromise) {
    webLLMProviderPromise = import('../../ai/providers/WebLLMProvider').then((m) => m.webLLMProvider)
  }
  return webLLMProviderPromise
}

/**
 * Angular port of React `useAiSettingsManager()`.
 *
 * `@Injectable()` without `providedIn`: list it in the consuming component's `providers`
 * (one instance per component, like a hook call). The initial load starts when the service is created.
 *
 * Same member names as the hook's return object: state → read-only signals, functions → methods.
 * Setters and handlers are arrow-function properties so they can be passed down as callbacks unchanged.
 */
@Injectable()
export class AiSettingsManagerService {
  private readonly toastService = inject(ToastService)
  private get toast() {
    return this.toastService.toast
  }

  private readonly _ai = signal<AISettings | null>(null)
  private readonly _loadingAi = signal(true)

  private readonly _provider = signal<string>('local')
  private readonly _model = signal<string>(DEFAULT_WEBLLM_MODEL)

  private readonly _isWritingOpen = signal(true)
  private readonly _isVoiceAudioOpen = signal(true)
  private readonly _showEndpointSection = signal(true)

  private readonly _catalogModels = signal<ModelCatalogItem[]>([])
  private readonly _catalogError = signal<string | null>(null)

  private readonly _voiceAudioProvider = signal<string>('local')
  private readonly _voiceAudioModel = signal<string>(DEFAULT_BROWSER_ASR_MODEL)
  private readonly _transcriptionGroqKey = signal('')
  private readonly _transcriptionOpenaiKey = signal('')
  private readonly _showTranscriptionKey = signal(false)

  private readonly _groqKey = signal('')
  private readonly _geminiKey = signal('')
  private readonly _openaiKey = signal('')
  private readonly _claudeKey = signal('')
  private readonly _ollamaUrl = signal('')
  private readonly _showKey = signal(false)

  private readonly _ollamaOnline = signal<boolean | null>(null)
  private readonly _ollamaModels = signal<string[]>([])
  private readonly _fetchingModels = signal(false)

  private readonly _savingAi = signal(false)
  private readonly _testingConnection = signal(false)
  private readonly configuredCreds = signal<string[]>([])

  // ── State (same names as the hook) ──────────────────────────────────────────
  readonly ai = this._ai.asReadonly()
  readonly loadingAi = this._loadingAi.asReadonly()
  readonly provider = this._provider.asReadonly()
  readonly model = this._model.asReadonly()
  readonly isWritingOpen = this._isWritingOpen.asReadonly()
  readonly showEndpointSection = this._showEndpointSection.asReadonly()
  readonly ollamaUrl = this._ollamaUrl.asReadonly()
  readonly ollamaOnline = this._ollamaOnline.asReadonly()
  readonly ollamaModels = this._ollamaModels.asReadonly()
  readonly fetchingModels = this._fetchingModels.asReadonly()
  readonly catalogModels = this._catalogModels.asReadonly()
  readonly catalogError = this._catalogError.asReadonly()
  readonly groqKey = this._groqKey.asReadonly()
  readonly geminiKey = this._geminiKey.asReadonly()
  readonly openaiKey = this._openaiKey.asReadonly()
  readonly claudeKey = this._claudeKey.asReadonly()
  readonly showKey = this._showKey.asReadonly()
  readonly savingAi = this._savingAi.asReadonly()
  readonly testingConnection = this._testingConnection.asReadonly()
  readonly voiceAudioProvider = this._voiceAudioProvider.asReadonly()
  readonly voiceAudioModel = this._voiceAudioModel.asReadonly()
  readonly transcriptionGroqKey = this._transcriptionGroqKey.asReadonly()
  readonly transcriptionOpenaiKey = this._transcriptionOpenaiKey.asReadonly()
  readonly showTranscriptionKey = this._showTranscriptionKey.asReadonly()
  readonly isVoiceAudioOpen = this._isVoiceAudioOpen.asReadonly()

  // ── Setters (same names as the hook) ────────────────────────────────────────
  readonly setProvider = (p: string): void => this._provider.set(p)
  readonly setModel = (m: string): void => this._model.set(m)
  readonly setIsWritingOpen = (open: boolean): void => this._isWritingOpen.set(open)
  readonly setShowEndpointSection = (show: boolean): void => this._showEndpointSection.set(show)
  readonly setOllamaUrl = (url: string): void => this._ollamaUrl.set(url)
  readonly setGroqKey = (k: string): void => this._groqKey.set(k)
  readonly setGeminiKey = (k: string): void => this._geminiKey.set(k)
  readonly setOpenaiKey = (k: string): void => this._openaiKey.set(k)
  readonly setClaudeKey = (k: string): void => this._claudeKey.set(k)
  readonly setShowKey = (show: boolean): void => this._showKey.set(show)
  readonly setVoiceAudioProvider = (p: string): void => this._voiceAudioProvider.set(p)
  readonly setVoiceAudioModel = (m: string): void => this._voiceAudioModel.set(m)
  readonly setTranscriptionGroqKey = (k: string): void => this._transcriptionGroqKey.set(k)
  readonly setTranscriptionOpenaiKey = (k: string): void => this._transcriptionOpenaiKey.set(k)
  readonly setShowTranscriptionKey = (show: boolean): void => this._showTranscriptionKey.set(show)
  readonly setIsVoiceAudioOpen = (open: boolean): void => this._isVoiceAudioOpen.set(open)

  private isMounted = true

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      this.isMounted = false
    })
    void this.load()
  }

  readonly loadDynamicCatalog = async (forceRefresh = false): Promise<void> => {
    try {
      const res = await api.getModelCatalog(forceRefresh)
      this._catalogError.set(res.error || null)
      this._catalogModels.set(res.models || [])
      if (res.models) {
        setDynamicClientCatalog(res.models)
      }
    } catch {
      this._catalogError.set('Error de conexión al cargar catálogo externo.')
      this._catalogModels.set([])
    }
  }

  readonly fetchOllamaModels = async (url?: string, isUserAction = false): Promise<void> => {
    this._fetchingModels.set(true)
    const target = normalizeOllamaUrl(url !== undefined ? url : this._ollamaUrl())
    try {
      const res = await api.listOllamaModels(target)
      this._ollamaOnline.set(res.online)
      this._ollamaModels.set(res.models || [])
      if (!res.online && isUserAction) {
        this.toast.error(`No se pudo conectar con el servidor Ollama remoto en "${target}".`)
      } else if (res.online && isUserAction) {
        this.toast.success(
          `Conexión exitosa con servidor Ollama remoto (${res.models?.length || 0} modelos disponibles).`,
        )
      }
    } catch (err) {
      this._ollamaOnline.set(false)
      this._ollamaModels.set([])
      if (isUserAction) {
        this.toast.error(
          `Error de conexión con Ollama remoto: ${err instanceof Error ? err.message : 'Error desconocido'}`,
        )
      }
    } finally {
      this._fetchingModels.set(false)
    }
  }

  private async load(): Promise<void> {
    this._loadingAi.set(true)
    try {
      await this.loadDynamicCatalog(false)
      const [settings, userPrefs, credsList] = await Promise.all([
        api.getAiSettings(),
        api.getUserPreferences().catch(() => null),
        api.listProviderCredentials().catch(() => []),
      ])
      if (!this.isMounted) return
      this._ai.set(settings)
      this.configuredCreds.set(credsList.map((c) => c.provider.toLowerCase()))
      const rawProv = userPrefs?.inference_provider || settings.provider || 'local'
      const effectiveProv = rawProv === 'builtin' ? 'local' : rawProv === 'ollama' ? 'ollama_remote' : rawProv
      this._provider.set(effectiveProv)

      const activeModel = userPrefs?.inference_model || settings.model
      this._model.set(activeModel || (effectiveProv === 'local' ? DEFAULT_WEBLLM_MODEL : 'llama-3.3-70b-versatile'))

      const rawTransProv = userPrefs?.transcription_provider || settings.transcription_provider || 'local'
      const effectiveTransProv = rawTransProv === 'builtin' || rawTransProv === 'browser_asr' ? 'local' : rawTransProv
      this._voiceAudioProvider.set(effectiveTransProv)

      const savedTransModel = userPrefs?.transcription_model || settings.transcription_model
      this._voiceAudioModel.set(
        savedTransModel || (effectiveTransProv === 'local' ? DEFAULT_BROWSER_ASR_MODEL : 'whisper-large-v3'),
      )

      if (settings.ollama_base_url) {
        this._ollamaUrl.set(settings.ollama_base_url)
        void this.fetchOllamaModels(settings.ollama_base_url, false)
      }
    } catch (err) {
      if (this.isMounted) {
        this.toast.error(err instanceof Error ? err.message : 'Error al cargar configuración.')
      }
    } finally {
      if (this.isMounted) {
        this._loadingAi.set(false)
      }
    }
  }

  private checkIsKeyConfigured(p: string): boolean {
    const ai = this._ai()
    if (this.configuredCreds().includes(p)) return true
    if (p === 'groq') return Boolean(ai?.groq_api_key_set)
    if (p === 'gemini') return Boolean(ai?.gemini_api_key_set)
    if (p === 'openai') return Boolean(ai?.openai_api_key_set)
    if (p === 'claude') return Boolean(ai?.claude_api_key_set)
    return true
  }

  private buildKeyPayload(payload: Record<string, string>): Record<string, string> {
    if (this._groqKey().trim()) payload['groq_api_key'] = this._groqKey().trim()
    if (this._geminiKey().trim()) payload['gemini_api_key'] = this._geminiKey().trim()
    if (this._openaiKey().trim()) payload['openai_api_key'] = this._openaiKey().trim()
    if (this._claudeKey().trim()) payload['claude_api_key'] = this._claudeKey().trim()
    return payload
  }

  private validateCurrent() {
    const provider = this._provider()
    return validateAiSettingsPayload({
      provider,
      model: this._model(),
      ollamaUrl: this._ollamaUrl(),
      groqKey: this._groqKey(),
      geminiKey: this._geminiKey(),
      openaiKey: this._openaiKey(),
      claudeKey: this._claudeKey(),
      isKeyConfigured: this.checkIsKeyConfigured(provider),
    })
  }

  readonly handleAiSave = async (event?: Event): Promise<void> => {
    if (event) event.preventDefault()

    const validation = this.validateCurrent()
    if (!validation.isValid) {
      this.toast.error(validation.error || 'Verifica los campos ingresados.')
      return
    }

    const provider = this._provider()
    const model = this._model()

    this._savingAi.set(true)
    const payload = this.buildKeyPayload({
      provider,
      model: model.trim(),
      inference_provider: provider,
      inference_model: model.trim(),
      ollama_base_url: normalizeOllamaUrl(this._ollamaUrl()),
    })

    try {
      const updated = await api.updateAiSettings(payload)
      this._ai.set(updated)
      inferenceService.setAiSettings(updated)
      await api
        .updateUserPreferences({
          inference_provider: provider,
          inference_model: model.trim(),
        })
        .catch(() => null)
      this._groqKey.set('')
      this._geminiKey.set('')
      this._openaiKey.set('')
      this._claudeKey.set('')
      this.toast.success('Configuración guardada exitosamente.')
    } catch (err) {
      this.toast.error(err instanceof Error ? err.message : 'Error al guardar la configuración.')
    } finally {
      this._savingAi.set(false)
    }
  }

  readonly handleTestConnection = async (): Promise<void> => {
    const validation = this.validateCurrent()
    if (!validation.isValid) {
      this.toast.error(validation.error || 'Verifica los campos ingresados.')
      return
    }

    const provider = this._provider()
    const model = this._model()

    this._testingConnection.set(true)
    if (provider === 'local' || provider === 'builtin') {
      try {
        const webllm = await getWebLLMProvider()
        const isCached = await webllm.isModelCached(model)
        if (!isCached) {
          this.toast.error(`El modelo ${model} no está descargado en la caché del navegador.`)
          return
        }
        await webllm.initModel(model)
        const answer = await webllm.complete([{ role: 'user', content: 'Responde únicamente con OK.' }], {
          maxTokens: 10,
        })
        this.toast.success(`Prueba exitosa con WebLLM (${model}): ${answer}`)
      } catch (err) {
        this.toast.error(err instanceof Error ? err.message : 'Error al probar modelo en navegador.')
      } finally {
        this._testingConnection.set(false)
      }
      return
    }

    const payload = this.buildKeyPayload({
      provider,
      model: model.trim(),
      ollama_base_url: normalizeOllamaUrl(this._ollamaUrl()),
    })

    try {
      const res = await api.testAiConnection(payload)
      if (res.ok || res.status === 'ok') {
        this.toast.success(res.message || 'Prueba de conexión exitosa.')
      } else {
        this.toast.error(res.message || 'La prueba de conexión ha fallado.')
      }
    } catch (err) {
      this.toast.error(err instanceof Error ? err.message : 'Error al probar conexión.')
    } finally {
      this._testingConnection.set(false)
    }
  }

  readonly handleVoiceAudioSave = async (event?: Event): Promise<void> => {
    if (event) event.preventDefault()
    this._savingAi.set(true)

    const voiceAudioProvider = this._voiceAudioProvider()
    const voiceAudioModel = this._voiceAudioModel()

    const payload: Record<string, string> = {
      transcription_provider: voiceAudioProvider,
      transcription_model: voiceAudioModel.trim(),
    }

    if (this._transcriptionGroqKey().trim()) {
      payload['transcription_groq_api_key'] = this._transcriptionGroqKey().trim()
    }
    if (this._transcriptionOpenaiKey().trim()) {
      payload['transcription_openai_api_key'] = this._transcriptionOpenaiKey().trim()
    }

    try {
      const updated = await api.updateAiSettings(payload)
      this._ai.set(updated)
      await api
        .updateUserPreferences({
          transcription_provider: voiceAudioProvider,
          transcription_model: voiceAudioModel.trim(),
        })
        .catch(() => null)
      this._transcriptionGroqKey.set('')
      this._transcriptionOpenaiKey.set('')
      this.toast.success('Configuración de transcripción guardada.')
    } catch (err) {
      this.toast.error(err instanceof Error ? err.message : 'Error al guardar configuración.')
    } finally {
      this._savingAi.set(false)
    }
  }
}
