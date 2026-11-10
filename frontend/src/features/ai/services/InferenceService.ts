import { api, type AISettings } from '../../../api/client'
import {
  DEFAULT_WEBLLM_MODEL,
  isSupportedWebLLMModel,
} from '../catalogs/clientCatalog'
import type {
  ArtifactGenerationRequest,
  ArtifactGenerationResult,
  ChatMessage,
  SummarizeRequest,
  SummarizeResult,
} from '../types/webLlm'

export type StreamChunkCallback = (chunk: string, accumulated: string) => void

let webLLMProvider: Awaited<typeof import('../providers/WebLLMProvider')>['webLLMProvider'] | null = null

async function getWebLLMProvider() {
  if (!webLLMProvider) {
    const module = await import('../providers/WebLLMProvider')
    webLLMProvider = module.webLLMProvider
  }
  return webLLMProvider
}

export class InferenceService {
  private static instance: InferenceService | null = null
  private cachedSettings: AISettings | null = null

  public static getInstance(): InferenceService {
    if (!InferenceService.instance) {
      InferenceService.instance = new InferenceService()
    }
    return InferenceService.instance
  }

  public setAiSettings(settings: AISettings | null): void {
    this.cachedSettings = settings
  }

  public async getAiSettings(): Promise<AISettings | null> {
    if (this.cachedSettings) {
      return this.cachedSettings
    }
    try {
      this.cachedSettings = await api.getAiSettings()
      return this.cachedSettings
    } catch {
      return null
    }
  }

  public isBrowserExecution(settings: AISettings | null): boolean {
    const provider = (settings?.provider || 'local').toLowerCase()
    return provider === 'local' || provider === 'builtin' || provider === 'webllm'
  }

  private resolveWebLLMModel(settings: AISettings | null): string {
    const configured = settings?.model || ''
    if (isSupportedWebLLMModel(configured)) {
      return configured
    }
    return DEFAULT_WEBLLM_MODEL
  }

  public async summarize(
    request: SummarizeRequest,
    onChunk?: StreamChunkCallback,
  ): Promise<SummarizeResult> {
    const settings = await this.getAiSettings()
    const messages = this.buildSummarizeMessages(request)

    if (this.isBrowserExecution(settings)) {
      const model = this.resolveWebLLMModel(settings)
      const output = await this.executeWebLLM(model, messages, onChunk, {
        maxTokens: request.maxTokens,
        temperature: request.temperature ?? 0.3,
      })
      return { summary: output, modelUsed: model }
    }

    const provider = settings?.provider || 'groq'
    const model = settings?.model || 'llama-3.3-70b-versatile'
    const output = await this.executeBackendPrompt(provider, model, messages, onChunk)
    return { summary: output, modelUsed: `${provider}:${model}` }
  }

  public async generateArtifact(
    request: ArtifactGenerationRequest,
    onChunk?: StreamChunkCallback,
  ): Promise<ArtifactGenerationResult> {
    const settings = await this.getAiSettings()
    const messages = this.buildArtifactMessages(request)

    if (this.isBrowserExecution(settings)) {
      const model = this.resolveWebLLMModel(settings)
      const output = await this.executeWebLLM(model, messages, onChunk, {
        maxTokens: request.maxTokens ?? 3072,
        temperature: request.temperature ?? 0.5,
      })
      return { content: output, modelUsed: model }
    }

    const provider = settings?.provider || 'groq'
    const model = settings?.model || 'llama-3.3-70b-versatile'
    const output = await this.executeBackendPrompt(provider, model, messages, onChunk)
    return { content: output, modelUsed: `${provider}:${model}` }
  }

  public async generateMessages(
    messages: ChatMessage[],
    onChunk?: StreamChunkCallback,
    options?: { maxTokens?: number; temperature?: number; autoContinue?: boolean; maxContinuations?: number },
  ): Promise<{ content: string; modelUsed: string }> {
    const settings = await this.getAiSettings()

    if (this.isBrowserExecution(settings)) {
      const model = this.resolveWebLLMModel(settings)
      const content = await this.executeWebLLM(model, messages, onChunk, options)
      return { content, modelUsed: model }
    }

    const provider = settings?.provider || 'groq'
    const model = settings?.model || 'llama-3.3-70b-versatile'
    const content = await this.executeBackendPrompt(provider, model, messages, onChunk)
    return { content, modelUsed: `${provider}:${model}` }
  }

  private buildSummarizeMessages(request: SummarizeRequest): ChatMessage[] {
    const systemContent =
      request.systemPrompt ||
      'Eres un analista de software experto en sintetizar requerimientos, decisiones y acuerdos.'

    const userPrompt = request.instructions
      ? `${request.instructions}\n\nTexto a resumir:\n${request.text}`
      : `Resume el siguiente contenido extrayendo puntos clave, decisiones y requerimientos:\n\n${request.text}`

    return [
      { role: 'system', content: systemContent },
      { role: 'user', content: userPrompt },
    ]
  }

  private buildArtifactMessages(request: ArtifactGenerationRequest): ChatMessage[] {
    const systemContent =
      request.systemPrompt ||
      'Eres un arquitecto de software y analista QA. Genera artefactos estructurados, directos y con alta fidelidad técnica.'

    const userContent = request.context
      ? `Contexto:\n${request.context}\n\nInstrucciones:\n${request.instructions}`
      : request.instructions

    return [
      { role: 'system', content: systemContent },
      { role: 'user', content: userContent },
    ]
  }

  private async executeWebLLM(
    modelId: string,
    messages: ChatMessage[],
    onChunk?: StreamChunkCallback,
    options?: { maxTokens?: number; temperature?: number; autoContinue?: boolean; maxContinuations?: number },
  ): Promise<string> {
    const provider = await getWebLLMProvider()

    if (provider.getActiveModelId() !== modelId) {
      await provider.initModel(modelId)
    }

    if (onChunk) {
      return provider.streamComplete(messages, onChunk, options)
    }
    return provider.complete(messages, options)
  }

  private async executeBackendPrompt(
    provider: string,
    model: string,
    messages: ChatMessage[],
    onChunk?: StreamChunkCallback,
  ): Promise<string> {
    const userMsg = messages.find((m) => m.role === 'user')?.content || ''
    const systemMsg = messages.find((m) => m.role === 'system')?.content || ''

    let accumulated = ''
    const res = await api.agenticPromptStream(
      {
        query: userMsg,
        current_document: systemMsg,
        provider,
        model,
      },
      (acc, chunk) => {
        accumulated = acc
        if (onChunk) {
          onChunk(chunk, acc)
        }
      },
    )

    return res.answer || accumulated
  }
}

export const inferenceService = InferenceService.getInstance()
