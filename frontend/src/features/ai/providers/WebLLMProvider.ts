import {
  CreateWebWorkerMLCEngine,
  hasModelInCache,
  deleteModelAllInfoInCache,
  type WebWorkerMLCEngine,
  type InitProgressReport,
  type ChatCompletionChunk,
} from '@mlc-ai/web-llm'
import { isSecureOrigin } from '../../../core/browser/secureContext'
import { acquireTabGpuLock, registerGpuConsumer, releaseOtherGpuConsumers } from '../../../core/gpu/gpuResources'
import {
  BrowserLlmError,
  browserLlmErrorMessage,
  classifyBrowserLlmError,
  toBrowserLlmError,
} from '../errors/browserLlmErrors'
import { findWebLLMModel } from '../policies/modelSelectionPolicy'
import type { ChatMessage, WebLLMInitProgress } from '../types/webLlm'
import { BROWSER_CONTEXT_TOKENS, fitPromptToContext } from '../utils/promptBudget'

type CompletionOptions = {
  maxTokens?: number
  temperature?: number
  autoContinue?: boolean
  maxContinuations?: number
}

/** Unload the model (and free its GPU memory and the cross-tab lock) after this much inactivity. */
export const LLM_IDLE_UNLOAD_MS = 10 * 60 * 1000
const GPU_CONSUMER = 'webllm'
const TAB_LOCK = 'funcassist-webllm-gpu'
/** Tighter estimate used when the first estimate still overflowed the context window. */
const STRICT_CHARS_PER_TOKEN = 2.4

/** Kept for existing callers: user-facing text for any WebLLM failure. */
export function formatWebLLMError(err: unknown): string {
  return toBrowserLlmError(err, null).message
}

function modelName(modelId: string | null): string | null {
  if (!modelId) return null
  return findWebLLMModel(modelId)?.name ?? modelId
}

function contextTokensFor(modelId: string | null): number {
  const configured = modelId ? findWebLLMModel(modelId)?.contextTokens : undefined
  return configured && configured > 0 ? configured : BROWSER_CONTEXT_TOKENS
}

export class WebLLMProvider {
  private static instance: WebLLMProvider | null = null
  private worker: Worker | null = null
  private engine: WebWorkerMLCEngine | null = null
  private loadedModelId: string | null = null
  private isInitializing = false
  private activeGenerations = 0
  private idleTimer: ReturnType<typeof setTimeout> | null = null
  private releaseTabLock: (() => void) | null = null

  constructor() {
    // Another GPU user (in-browser Whisper) asks for memory: unload unless a generation is running.
    registerGpuConsumer(GPU_CONSUMER, async () => {
      if (this.activeGenerations === 0 && !this.isInitializing) await this.unload()
    })
  }

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

  public async initModel(modelId: string, onProgress?: (report: WebLLMInitProgress) => void): Promise<void> {
    if (this.engine && this.loadedModelId === modelId) {
      this.touch()
      return
    }
    if (!isSecureOrigin()) {
      throw new BrowserLlmError('insecure_context', browserLlmErrorMessage('insecure_context'), modelId)
    }
    if (this.isInitializing) {
      throw new Error('Ya hay una inicialización de modelo en progreso.')
    }

    this.isInitializing = true
    try {
      if (this.engine) await this.unloadEngine()
      // Free GPU memory held by other in-browser models (e.g. an idle Whisper worker) first.
      await releaseOtherGpuConsumers(GPU_CONSUMER)
      if (!this.releaseTabLock) {
        const release = await acquireTabGpuLock(TAB_LOCK)
        if (!release) {
          throw new BrowserLlmError('busy_other_tab', browserLlmErrorMessage('busy_other_tab'), modelId)
        }
        this.releaseTabLock = release
      }
      await this.ensureEngine(modelId, onProgress)
      this.loadedModelId = modelId
      this.touch()
    } catch (err) {
      const wrapped = toBrowserLlmError(err, modelId, modelName(modelId))
      await this.unload()
      throw wrapped
    } finally {
      this.isInitializing = false
    }
  }

  private async ensureEngine(modelId: string, onProgress?: (report: WebLLMInitProgress) => void): Promise<void> {
    if (!this.worker) {
      this.worker = new Worker(new URL('../../../workers/llm.worker.ts', import.meta.url), { type: 'module' })
    }

    const progressHandler = (report: InitProgressReport): void => {
      onProgress?.({
        progress: Math.round(report.progress * 100),
        text: report.text,
        timeElapsed: report.timeElapsed,
      })
    }

    // The context window is explicit: it sizes the KV cache in GPU memory, and prompts are budgeted
    // against the same value.
    this.engine = await CreateWebWorkerMLCEngine(
      this.worker,
      modelId,
      { initProgressCallback: progressHandler },
      { context_window_size: contextTokensFor(modelId) },
    )
  }

  private touch(): void {
    if (this.idleTimer) clearTimeout(this.idleTimer)
    this.idleTimer = setTimeout(() => {
      this.idleTimer = null
      if (this.activeGenerations === 0 && !this.isInitializing) void this.unload()
    }, LLM_IDLE_UNLOAD_MS)
  }

  private requireEngine(): WebWorkerMLCEngine {
    if (!this.engine) {
      throw new Error('El motor de WebLLM no está inicializado. Descarga y selecciona un modelo primero.')
    }
    return this.engine
  }

  /**
   * Runs one generation with prompts fitted to the context window. If the model still reports a
   * context overflow (the estimate is approximate), retries once with a stricter estimate.
   */
  private async withFittedPrompt<T>(
    messages: ChatMessage[],
    requestedOutput: number | undefined,
    run: (fitted: ChatMessage[], maxTokens: number) => Promise<T>,
  ): Promise<T> {
    const contextTokens = contextTokensFor(this.loadedModelId)
    const first = fitPromptToContext(messages, contextTokens, requestedOutput)
    if (first.trimmed) {
      console.warn(`[WebLLM] Prompt recortado a ~${first.promptTokens} tokens para caber en ${contextTokens}.`)
    }
    try {
      return await run(first.messages, first.maxTokens)
    } catch (err) {
      if (classifyBrowserLlmError(err) !== 'context_window') throw err
      const strict = fitPromptToContext(messages, contextTokens, requestedOutput, STRICT_CHARS_PER_TOKEN)
      return run(strict.messages, strict.maxTokens)
    }
  }

  public async complete(messages: ChatMessage[], options?: CompletionOptions): Promise<string> {
    const engine = this.requireEngine()
    this.activeGenerations += 1
    try {
      return await this.withFittedPrompt(messages, options?.maxTokens, async (fitted, maxTokens) => {
        const response = await engine.chat.completions.create({
          messages: fitted,
          max_tokens: maxTokens,
          temperature: options?.temperature ?? 0.7,
          stream: false,
        })
        return response.choices[0]?.message?.content || ''
      })
    } catch (err) {
      const wrapped = toBrowserLlmError(err, this.loadedModelId, modelName(this.loadedModelId))
      if (wrapped.kind !== 'context_window') await this.unload()
      throw wrapped
    } finally {
      this.activeGenerations -= 1
      this.touch()
    }
  }

  public async streamComplete(
    messages: ChatMessage[],
    onChunk: (chunk: string, accumulated: string) => void,
    options?: CompletionOptions,
  ): Promise<string> {
    const engine = this.requireEngine()
    const maxContinuations = options?.maxContinuations ?? 3
    let accumulated = ''
    let continuationMessages = messages
    this.activeGenerations += 1

    try {
      for (let attempt = 0; attempt <= (options?.autoContinue ? maxContinuations : 0); attempt += 1) {
        const finishReason = await this.withFittedPrompt(
          continuationMessages,
          options?.maxTokens,
          async (fitted, maxTokens): Promise<string | null> => {
            const stream = await engine.chat.completions.create({
              messages: fitted,
              max_tokens: maxTokens,
              temperature: options?.temperature ?? 0.7,
              stream: true,
            })
            let reason: string | null = null
            for await (const chunk of stream as AsyncIterable<ChatCompletionChunk>) {
              reason = chunk.choices[0]?.finish_reason || reason
              const delta = chunk.choices[0]?.delta?.content || ''
              if (delta) {
                accumulated += delta
                onChunk(delta, accumulated)
              }
            }
            return reason
          },
        )

        if (finishReason !== 'length' || attempt >= maxContinuations) break

        // Continue with the last part of the answer only: resending everything would overflow
        // the 4,096-token window after the first continuation.
        continuationMessages = [
          ...messages,
          { role: 'assistant', content: accumulated.slice(-2000) } as ChatMessage,
          {
            role: 'user',
            content: 'Continúa exactamente desde el último punto sin repetir contenido. Finaliza el documento completo.',
          },
        ]
      }
      return accumulated
    } catch (err) {
      const wrapped = toBrowserLlmError(err, this.loadedModelId, modelName(this.loadedModelId))
      if (wrapped.kind !== 'context_window') await this.unload()
      if (accumulated && wrapped.kind === 'context_window') return accumulated
      throw wrapped
    } finally {
      this.activeGenerations -= 1
      this.touch()
    }
  }

  private async unloadEngine(): Promise<void> {
    if (this.engine) {
      try {
        await this.engine.unload()
      } catch {
        // Engine already disposed
      }
      this.engine = null
    }
  }

  public async unload(): Promise<void> {
    if (this.idleTimer) clearTimeout(this.idleTimer)
    this.idleTimer = null
    await this.unloadEngine()
    if (this.worker) {
      this.worker.terminate()
      this.worker = null
    }
    this.loadedModelId = null
    if (this.releaseTabLock) {
      this.releaseTabLock()
      this.releaseTabLock = null
    }
  }

  public getActiveModelId(): string | null {
    return this.loadedModelId
  }
}

export const webLLMProvider = WebLLMProvider.getInstance()
