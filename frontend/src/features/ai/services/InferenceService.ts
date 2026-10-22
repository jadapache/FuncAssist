import { api, type AISettings } from '../../../api/client'
import { webLLMProvider } from '../providers/WebLLMProvider'
import type {
  ArtifactGenerationRequest,
  ArtifactGenerationResult,
  ChatMessage,
  SummarizeRequest,
  SummarizeResult,
} from '../types/webLlm'

export type StreamChunkCallback = (chunk: string, accumulated: string) => void

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

  private resolveProvider(settings: AISettings | null): string {
    return settings?.provider || 'builtin'
  }

  private resolveModel(settings: AISettings | null): string {
    return settings?.model || 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC'
  }

  public async summarize(
    request: SummarizeRequest,
    onChunk?: StreamChunkCallback,
  ): Promise<SummarizeResult> {
    const settings = await this.getAiSettings()
    const provider = this.resolveProvider(settings)
    const model = this.resolveModel(settings)

    const messages = this.buildSummarizeMessages(request)

    if (provider === 'builtin') {
      const output = await this.executeWebLLM(model, messages, onChunk, {
        maxTokens: request.maxTokens,
        temperature: request.temperature ?? 0.3,
      })
      return { summary: output, modelUsed: model }
    }

    const output = await this.executeBackendPrompt(messages, onChunk)
    return { summary: output, modelUsed: `${provider}:${model}` }
  }

  public async generateArtifact(
    request: ArtifactGenerationRequest,
    onChunk?: StreamChunkCallback,
  ): Promise<ArtifactGenerationResult> {
    const settings = await this.getAiSettings()
    const provider = this.resolveProvider(settings)
    const model = this.resolveModel(settings)

    const messages = this.buildArtifactMessages(request)

    if (provider === 'builtin') {
      const output = await this.executeWebLLM(model, messages, onChunk, {
        maxTokens: request.maxTokens ?? 3072,
        temperature: request.temperature ?? 0.5,
      })
      return { content: output, modelUsed: model }
    }

    const output = await this.executeBackendPrompt(messages, onChunk)
    return { content: output, modelUsed: `${provider}:${model}` }
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
    options?: { maxTokens?: number; temperature?: number },
  ): Promise<string> {
    if (webLLMProvider.getActiveModelId() !== modelId) {
      await webLLMProvider.initModel(modelId)
    }

    if (onChunk) {
      return webLLMProvider.streamComplete(messages, onChunk, options)
    }
    return webLLMProvider.complete(messages, options)
  }

  private async executeBackendPrompt(
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
