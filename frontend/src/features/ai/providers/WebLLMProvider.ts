import {
  CreateWebWorkerMLCEngine,
  hasModelInCache,
  deleteModelAllInfoInCache,
  type WebWorkerMLCEngine,
  type InitProgressReport,
  type ChatCompletionChunk,
} from '@mlc-ai/web-llm'
import type { ChatMessage, WebLLMInitProgress } from '../types/webLlm'

export class WebLLMProvider {
  private static instance: WebLLMProvider | null = null
  private worker: Worker | null = null
  private engine: WebWorkerMLCEngine | null = null
  private loadedModelId: string | null = null
  private isInitializing: boolean = false

  public static getInstance(): WebLLMProvider {
    if (!WebLLMProvider.instance) {
      WebLLMProvider.instance = new WebLLMProvider()
    }
    return WebLLMProvider.instance
  }

  public async isModelCached(modelId: string): Promise<boolean> {
    try {
      return await hasModelInCache(modelId)
    } catch {
      return false
    }
  }

  public async deleteCachedModel(modelId: string): Promise<void> {
    if (this.loadedModelId === modelId) {
      await this.unload()
    }
    await deleteModelAllInfoInCache(modelId)
  }

  public async initModel(
    modelId: string,
    onProgress?: (report: WebLLMInitProgress) => void,
  ): Promise<void> {
    if (this.engine && this.loadedModelId === modelId) {
      return
    }

    if (this.isInitializing) {
      throw new Error('Ya hay una inicialización de modelo en progreso.')
    }

    this.isInitializing = true
    try {
      await this.ensureEngine(modelId, onProgress)
      this.loadedModelId = modelId
    } finally {
      this.isInitializing = false
    }
  }

  private async ensureEngine(
    modelId: string,
    onProgress?: (report: WebLLMInitProgress) => void,
  ): Promise<void> {
    if (!this.worker) {
      this.worker = new Worker(
        new URL('../../../workers/llm.worker.ts', import.meta.url),
        { type: 'module' },
      )
    }

    const progressHandler = (report: InitProgressReport): void => {
      if (onProgress) {
        onProgress({
          progress: Math.round(report.progress * 100),
          text: report.text,
          timeElapsed: report.timeElapsed,
        })
      }
    }

    this.engine = await CreateWebWorkerMLCEngine(this.worker, modelId, {
      initProgressCallback: progressHandler,
    })
  }

  public async complete(
    messages: ChatMessage[],
    options?: { maxTokens?: number; temperature?: number },
  ): Promise<string> {
    if (!this.engine) {
      throw new Error('El motor de WebLLM no está inicializado. Descarga y selecciona un modelo primero.')
    }

    const response = await this.engine.chat.completions.create({
      messages,
      max_tokens: options?.maxTokens ?? 2048,
      temperature: options?.temperature ?? 0.7,
      stream: false,
    })

    return response.choices[0]?.message?.content || ''
  }

  public async streamComplete(
    messages: ChatMessage[],
    onChunk: (chunk: string, accumulated: string) => void,
    options?: { maxTokens?: number; temperature?: number },
  ): Promise<string> {
    if (!this.engine) {
      throw new Error('El motor de WebLLM no está inicializado.')
    }

    const stream = await this.engine.chat.completions.create({
      messages,
      max_tokens: options?.maxTokens ?? 2048,
      temperature: options?.temperature ?? 0.7,
      stream: true,
    })

    let accumulated = ''
    for await (const chunk of stream as AsyncIterable<ChatCompletionChunk>) {
      const delta = chunk.choices[0]?.delta?.content || ''
      if (delta) {
        accumulated += delta
        onChunk(delta, accumulated)
      }
    }

    return accumulated
  }

  public async unload(): Promise<void> {
    if (this.engine) {
      await this.engine.unload()
      this.engine = null
    }
    if (this.worker) {
      this.worker.terminate()
      this.worker = null
    }
    this.loadedModelId = null
  }

  public getActiveModelId(): string | null {
    return this.loadedModelId
  }
}

export const webLLMProvider = WebLLMProvider.getInstance()
