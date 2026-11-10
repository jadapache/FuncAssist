import {
  CreateWebWorkerMLCEngine,
  hasModelInCache,
  deleteModelAllInfoInCache,
  type WebWorkerMLCEngine,
  type InitProgressReport,
  type ChatCompletionChunk,
} from '@mlc-ai/web-llm'
import type { ChatMessage, WebLLMInitProgress } from '../types/webLlm'
import { findWebLLMModel } from '../policies/modelSelectionPolicy'

type CompletionOptions = {
  maxTokens?: number
  temperature?: number
  autoContinue?: boolean
  maxContinuations?: number
}

function resolveGenerationBudget(modelId: string, messages: ChatMessage[], requested?: number): number {
  const model = findWebLLMModel(modelId)
  const contextWindow = Number.parseInt(model?.contextWindow.replace(/[^0-9]/g, '') || '8192', 10)
  const inputTokens = Math.ceil(messages.reduce((total, message) => total + message.content.length, 0) / 4)
  const availableTokens = Math.max(512, contextWindow - inputTokens - 256)
  const modelSafeLimit = Math.min(8192, availableTokens)
  return Math.max(512, Math.min(requested ?? modelSafeLimit, modelSafeLimit))
}

export function formatWebLLMError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err || '')
  if (
    /device\s*(was\s*)?lost|gpu\s*device\s*lost|dxgi_error|device_hung|0x887a0006|already\s*been\s*disposed|insufficient\s*memory|out\s*of\s*memory/i.test(
      message,
    )
  ) {
    return 'La tarjeta gráfica (GPU/VRAM) se quedó sin memoria o se desconectó al ejecutar el modelo en el navegador. Por favor selecciona un modelo más ligero (ej. Llama 3.2 1B) en Configuración o utiliza un proveedor externo (Ollama o API en la nube).'
  }
  if (/webgpu/i.test(message) && /not\s*supported|unsupported|unavailable/i.test(message)) {
    return 'Tu navegador o dispositivo no cuenta con aceleración WebGPU activa para ejecutar modelos locales.'
  }
  if (/contextwindowsizeexceeded|prompt tokens exceed context window/i.test(message)) {
    return 'La transcripción supera la ventana de contexto de este modelo en el navegador. Para textos muy extensos te sugerimos seleccionar Google Gemini (1M+ tokens) o un modelo de nube en Configuración.'
  }
  return message || 'Error al ejecutar el modelo de lenguaje en el navegador.'
}

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
    } catch (err) {
      await this.unload()
      throw new Error(formatWebLLMError(err))
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
    options?: CompletionOptions,
  ): Promise<string> {
    if (!this.engine) {
      throw new Error('El motor de WebLLM no está inicializado. Descarga y selecciona un modelo primero.')
    }

    try {
      const response = await this.engine.chat.completions.create({
        messages,
        max_tokens: resolveGenerationBudget(this.loadedModelId || '', messages, options?.maxTokens),
        temperature: options?.temperature ?? 0.7,
        stream: false,
      })

      return response.choices[0]?.message?.content || ''
    } catch (err) {
      await this.unload()
      throw new Error(formatWebLLMError(err))
    }
  }

  public async streamComplete(
    messages: ChatMessage[],
    onChunk: (chunk: string, accumulated: string) => void,
    options?: CompletionOptions,
  ): Promise<string> {
    if (!this.engine) {
      throw new Error('El motor de WebLLM no está inicializado.')
    }

    const maxContinuations = options?.maxContinuations ?? 3
    let accumulated = ''
    let continuationMessages = messages

    try {
      for (let attempt = 0; attempt <= (options?.autoContinue ? maxContinuations : 0); attempt += 1) {
        const stream = await this.engine.chat.completions.create({
          messages: continuationMessages,
          max_tokens: resolveGenerationBudget(this.loadedModelId || '', continuationMessages, options?.maxTokens),
          temperature: options?.temperature ?? 0.7,
          stream: true,
        })

        let finishReason: string | null = null
        for await (const chunk of stream as AsyncIterable<ChatCompletionChunk>) {
          finishReason = chunk.choices[0]?.finish_reason || finishReason
          const delta = chunk.choices[0]?.delta?.content || ''
          if (delta) {
            accumulated += delta
            onChunk(delta, accumulated)
          }
        }

        if (finishReason !== 'length' || attempt >= maxContinuations) {
          break
        }

        continuationMessages = [
          ...messages,
          { role: 'assistant', content: accumulated } as ChatMessage,
          {
            role: 'user',
            content: 'Continúa exactamente desde el último punto sin repetir contenido. Finaliza el documento completo.',
          },
        ]
      }

      return accumulated
    } catch (err) {
      await this.unload()
      throw new Error(formatWebLLMError(err))
    }
  }

  public async unload(): Promise<void> {
    if (this.engine) {
      try {
        await this.engine.unload()
      } catch {
        // Engine already disposed
      }
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
