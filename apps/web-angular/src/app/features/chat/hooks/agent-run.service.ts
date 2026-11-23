import { Injectable, signal } from '@angular/core'
import type { AgenticPromptResponse } from '../../../api/client'
import { api } from '../../../api/client'
import { inferenceService } from '../../ai/services/InferenceService'
import type { ChatMessage } from '../../ai/types/webLlm'
import { docAgentApi, type AgenticPromptPayload } from '../api/docAgentApi'
import type { AgentEventEnvelope, AgentRunState } from '../types/agentEvents'
import { INITIAL_RUN_STATE, processIncomingEvent } from './agentEventReducer'

/**
 * Angular port of React `useAgentRun`.
 * Per-component state (React hook) → `@Injectable()` without `providedIn`: list it in the
 * consumer's `providers` (it is injected by `AgenticGenerationService`).
 *
 * Execution path is decided per run exactly like React:
 * - browser execution (WebLLM / builtin provider) → `inferenceService.generateMessages` with the feature prompt/rubric;
 * - otherwise → backend SSE stream (`docAgentApi.agenticPromptStream`) with abort support.
 */
@Injectable()
export class AgentRunService {
  private readonly _runState = signal<AgentRunState>(INITIAL_RUN_STATE)
  readonly runState = this._runState.asReadonly()

  private abortController: AbortController | null = null
  private activeRunId: string | null = null
  private activeConvId: string | null = null

  resetRun(): void {
    this.abortController?.abort()
    this.abortController = null
    this.activeRunId = null
    this.activeConvId = null
    this._runState.set(INITIAL_RUN_STATE)
  }

  private handleEvent = (event: AgentEventEnvelope): void => {
    this._runState.update((prev) => processIncomingEvent(prev, event))
  }

  cancelRun = async (): Promise<void> => {
    const currentRunId = this.activeRunId || this._runState().runId
    const currentConvId = this.activeConvId || this._runState().conversationId

    // Abort local streaming reader immediately for instant UI responsiveness
    this.abortController?.abort()
    this.abortController = null

    this._runState.update((prev) => ({
      ...prev,
      status: 'cancelled',
      activeStatusText: 'Cancelado por el usuario',
    }))

    if (currentRunId) {
      await docAgentApi.cancelRun(currentRunId, currentConvId || undefined)
    }
  }

  async executeRun(
    payload: AgenticPromptPayload,
    onChunk: (accumulated: string, delta: string) => void,
    onIntent?: (intent: string) => void,
  ): Promise<AgenticPromptResponse> {
    const controller = new AbortController()
    this.abortController = controller

    const generatedRunId = payload.run_id || `run-${crypto.randomUUID().slice(0, 8)}`
    const targetConvId = payload.conversation_id || null
    this.activeRunId = generatedRunId
    this.activeConvId = targetConvId

    this._runState.set({
      ...INITIAL_RUN_STATE,
      runId: generatedRunId,
      conversationId: targetConvId,
      status: 'running',
      activeStatusText: 'Iniciando agente...',
    })

    try {
      const settings = await inferenceService.getAiSettings()
      if (inferenceService.isBrowserExecution(settings)) {
        const requestedFeature = payload.feature || 'builtin_agent'
        const [prompt, rubric] = await Promise.all([
          api.getAiPrompt(requestedFeature).catch(() => api.getAiPrompt('builtin_agent')),
          api.getAiRubric(requestedFeature).catch(() => null),
        ])
        const contextParts = [
          payload.current_document ? `Documento actual:\n${payload.current_document}` : '',
          payload.chat_context?.length ? `Conversación reciente:\n${payload.chat_context.join('\n')}` : '',
          payload.attached_docs?.length
            ? `Documentos adjuntos:\n${payload.attached_docs.map((doc) => `${doc.filename}:\n${doc.content}`).join('\n\n')}`
            : '',
        ].filter(Boolean)
        const context = contextParts.join('\n\n')
        const templateValues: Record<string, string> = {
          query: payload.query,
          context,
          chat_context: payload.chat_context?.join('\n') || '',
          rubric: rubric?.criteria?.map((criterion) => `- ${criterion}`).join('\n') || '',
        }
        const userTemplate = prompt.user_template?.trim() || '{query}'
        const userContent = userTemplate.replace(
          /\{(query|context|chat_context|rubric)\}/g,
          (_, key: string) => templateValues[key] || '',
        )
        const messages: ChatMessage[] = [
          {
            role: 'system',
            content: prompt.system?.trim() || '',
          },
          {
            role: 'user',
            content: userContent,
          },
        ]
        const result = await inferenceService.generateMessages(
          messages,
          (chunk, accumulated) => onChunk(accumulated, chunk),
          { temperature: 0.4, autoContinue: true, maxContinuations: 3 },
        )
        const response: AgenticPromptResponse = {
          answer: result.content,
          assistant_message: result.content,
          document_updates: result.content,
          intent_detected: payload.mode || 'client_builtin',
          requires_document_mutation: false,
          operations: [],
          planned_operations: [],
          artifacts: [],
        }
        this._runState.update((prev) => ({ ...prev, status: 'completed', activeStatusText: 'Listo' }))
        return response
      }
      return await docAgentApi.agenticPromptStream(
        { ...payload, run_id: generatedRunId },
        onChunk,
        onIntent,
        this.handleEvent,
        controller.signal,
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error en la ejecución'
      this._runState.update((prev) => ({
        ...prev,
        status: prev.status === 'cancelled' ? 'cancelled' : 'failed',
        errorMessage: message,
      }))
      throw err
    } finally {
      this.activeRunId = null
      this.activeConvId = null
      this.abortController = null
    }
  }
}
