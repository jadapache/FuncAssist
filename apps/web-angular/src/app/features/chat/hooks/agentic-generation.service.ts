/**
 * Servicio que encapsula el ciclo completo de generación agentic:
 * prompt del usuario → llamada al backend → streaming en vivo en el chat → actualización de estado.
 *
 * Angular port of React `useAgenticGeneration`. Per-component state → `@Injectable()` without
 * `providedIn`; the consumer lists `[AgenticGenerationService, AgentRunService]` in `providers`
 * and calls `init(options)` once (hook options → getters so values are read at send time,
 * exactly like the React callback closure).
 */
import { Injectable, computed, inject, signal } from '@angular/core'
import type { Artifact } from '../../../types/artifacts'
import { parseStreamForChatAndArtifacts } from '../../../utils/artifactSplitter'
import type { UniverAdapter } from '../../document/agent/adapters/UniverAdapter'
import type { DocumentAgent } from '../../document/agent/core/DocumentAgent'
import type { CanonicalDocumentOperation } from '../../document/agent/core/types'
import type { EphemeralAttachmentDoc } from '../api/docAgentApi'
import type {
  ChatAttachment,
  ChatConversation,
  ChatConversationUpdate,
  ChatPersistMessage,
  DocumentArtifact,
} from '../types/chat'
import { AgentRunService } from './agent-run.service'
import {
  classifyAgenticError,
  extractFinalArtifacts,
  formatNowTime,
  mergeStreamingArtifacts,
  reconcileGeneratedArtifacts,
  resolveAssistantBubbleText,
  resolveDocTitle,
  resolveIntentAndStatus,
  resolveIntentStatus,
  type AgenticErrorCategory,
  type AgenticGenerationConfig,
} from './agenticGenerationLogic'

export type { AgenticGenerationConfig } from './agenticGenerationLogic'

export interface AgenticGenerationOptions {
  config: () => AgenticGenerationConfig | undefined
  templateContent: () => string
  templateId: () => string | null
  sources: () => string[]
  activeConversation: () => ChatConversation | null
  activeArtifact: () => Artifact | null
  activeArtifactId: () => string | null
  artifacts: () => Artifact[]
  docHistoryContent: () => string
  adapter: UniverAdapter
  agent: DocumentAgent
  onUpdateConversation: (updates: ChatConversationUpdate, targetId?: string) => void
  onSetActiveArtifactId: (id: string) => void
  onDocHistoryPush: (content: string) => void
  onDocHistoryReset: (content: string) => void
  onSetDocPanelCollapsed: (v: boolean) => void
  onScrollToBottom: () => void
  createConversation: (name?: string) => ChatConversation
  renameConversation: (id: string, name: string) => void
  onResetPromptInputs?: () => void
  onError?: (errorMessage: string, isAuthError: boolean, errorCategory?: AgenticErrorCategory) => void
}

export type AttachedImageInput = { name: string; dataUrl: string; size?: number }

@Injectable()
export class AgenticGenerationService {
  private readonly agentRun = inject(AgentRunService)
  private opts: AgenticGenerationOptions | null = null

  private readonly _isGenerating = signal(false)
  private readonly _generatingConversationId = signal<string | null>(null)
  private readonly _streamingText = signal('')
  private readonly _generationStatus = signal('Pensando...')

  readonly isGenerating = this._isGenerating.asReadonly()
  readonly generatingConversationId = this._generatingConversationId.asReadonly()
  readonly streamingText = this._streamingText.asReadonly()
  readonly runState = this.agentRun.runState
  readonly generationStatus = computed(() => this.runState().activeStatusText || this._generationStatus())
  readonly liveThinkingSteps = computed(() => this.runState().steps)

  /** Hook options (React `useAgenticGeneration(opts)`). */
  init(options: AgenticGenerationOptions): void {
    this.opts = options
  }

  handleCancelRun = (): Promise<void> => this.agentRun.cancelRun()

  handleSendMessage = async (
    customQuery?: string,
    attachedImages?: AttachedImageInput[],
    attachedDocs?: EphemeralAttachmentDoc[],
  ): Promise<void> => {
    const opts = this.opts
    if (!opts) throw new Error('AgenticGenerationService.init() must be called before handleSendMessage()')

    const queryText = (customQuery || '').trim()
    if (
      (!queryText &&
        (!attachedImages || attachedImages.length === 0) &&
        (!attachedDocs || attachedDocs.length === 0)) ||
      this._isGenerating()
    ) {
      return
    }

    // Snapshot of the hook inputs at send time (React read them from the render closure).
    const config = opts.config()
    const templateContent = opts.templateContent()
    const templateId = opts.templateId()
    const sources = opts.sources()
    const activeConversation = opts.activeConversation()
    const activeArtifact = opts.activeArtifact()
    const docHistoryContent = opts.docHistoryContent()
    const { adapter, agent } = opts

    this._isGenerating.set(true)
    this._streamingText.set('')
    opts.onResetPromptInputs?.()

    const userMsgId = crypto.randomUUID()
    const now = formatNowTime()

    const docAttachments: ChatAttachment[] = (attachedDocs || []).map((doc) => ({
      id: doc.id,
      name: doc.filename,
      type: 'file',
      size: doc.char_count,
      content: doc.content,
    }))

    const imgAttachments: ChatAttachment[] = (attachedImages || []).map((img, idx) => ({
      id: `att-${idx}-${Date.now()}`,
      name: img.name,
      type: 'image',
      dataUrl: img.dataUrl,
      size: img.size,
    }))

    const allAttachments = [...imgAttachments, ...docAttachments]

    const userMessage: ChatPersistMessage = {
      id: userMsgId,
      role: 'user',
      content: queryText || (allAttachments.length > 0 ? 'Documentos e imágenes adjuntas' : ''),
      timestamp: now,
      attachments: allAttachments.length > 0 ? allAttachments : undefined,
    }

    let targetConv = activeConversation
    const titleSeed = queryText || attachedDocs?.[0]?.filename || 'Consulta'
    if (!targetConv) {
      const convTitle = titleSeed.length > 28 ? `${titleSeed.slice(0, 28)}...` : titleSeed
      targetConv = opts.createConversation(convTitle)
    } else if (
      targetConv.messages.length === 0 &&
      (targetConv.name === 'Nueva conversación' || targetConv.name.startsWith('Conversación '))
    ) {
      const convTitle = titleSeed.length > 28 ? `${titleSeed.slice(0, 28)}...` : titleSeed
      opts.renameConversation(targetConv.id, convTitle)
    }

    const targetConvId = targetConv.id
    this._generatingConversationId.set(targetConvId)
    const currentMsgs = targetConv?.messages ?? []
    const updatedMsgs = [...currentMsgs, userMessage]
    opts.onUpdateConversation({ messages: updatedMsgs, lastInteraction: new Date().toISOString() }, targetConvId)
    opts.onScrollToBottom()

    const defaultFeature = config?.uploadTags || config?.slug || 'chat'
    const resolution = resolveIntentAndStatus(queryText, defaultFeature, templateId)
    this._generationStatus.set(resolution.initialStatus)

    try {
      const currentDocContent = docHistoryContent || activeArtifact?.content || templateContent || ''
      let latestAccumulatedText = ''
      let liveIntent = resolution.targetFeature

      const res = await this.agentRun.executeRun(
        {
          query: queryText,
          feature: resolution.targetFeature,
          mode: resolution.targetMode,
          images: attachedImages?.map((img) => ({
            name: img.name,
            data: img.dataUrl,
          })),
          attached_docs: attachedDocs?.map((d) => ({
            filename: d.filename,
            content: d.content || '',
          })),
          current_document: currentDocContent,
          template_id: templateId || undefined,
          chat_context: currentMsgs.slice(-4).map((m) => `${m.role}: ${m.content}`),
          sources,
          conversation_id: targetConvId,
        },
        (accumulatedText) => {
          latestAccumulatedText = accumulatedText

          const parsedStream = parseStreamForChatAndArtifacts(
            accumulatedText,
            resolveDocTitle(config),
            'docx',
            templateContent,
          )

          if (!parsedStream.isConversational && parsedStream.artifacts.length > 0) {
            this._streamingText.set(parsedStream.chatText)
            opts.onSetDocPanelCollapsed(false)

            const baseList = [...((targetConv?.artifacts || []) as Artifact[])]
            const mergedList = mergeStreamingArtifacts(parsedStream.artifacts, baseList)

            opts.onUpdateConversation(
              {
                artifacts: mergedList as DocumentArtifact[],
                documentContent: parsedStream.artifacts[0]?.content || accumulatedText,
              },
              targetConvId,
            )

            if (parsedStream.artifacts[0]?.content) {
              opts.onDocHistoryPush(parsedStream.artifacts[0].content)
            }
          } else {
            this._streamingText.set(parsedStream.chatText || accumulatedText)
          }
        },
        (intent) => {
          liveIntent = intent
          this._generationStatus.set(resolveIntentStatus(intent))
        },
      )

      const candidateContent = res.document_updates || res.answer || latestAccumulatedText
      if (!candidateContent || !candidateContent.trim()) {
        throw new Error(
          'El modelo no generó contenido para la respuesta. Verifica la conexión y tu clave de API en Configuración.',
        )
      }

      const detectedIntent = res.intent_detected || liveIntent
      const hasExplicitArtifacts = (res.artifacts && res.artifacts.length > 0) || candidateContent.includes('<artifact')
      const isChatIntent = resolution.isChatOnly || (detectedIntent === 'chat' && !hasExplicitArtifacts)

      if (isChatIntent) {
        const rawChat = res.assistant_message || res.answer || candidateContent
        const cleanChat = rawChat.replace(/<\/?chat>/gi, '').trim()
        const assistantMessage: ChatPersistMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: cleanChat,
          timestamp: formatNowTime(),
        }

        opts.onUpdateConversation(
          {
            messages: [...updatedMsgs, assistantMessage],
          },
          targetConvId,
        )
        this._streamingText.set('')
        this._isGenerating.set(false)
        return
      }

      let finalContent = candidateContent
      const rawOps = (res.operations ?? res.planned_operations ?? []) as unknown[]
      const operations = rawOps.filter(
        (op): op is CanonicalDocumentOperation => typeof op === 'object' && op !== null && 'operation' in op,
      )

      if (operations.length > 0) {
        await adapter.loadTemplate(currentDocContent, 'document', resolveDocTitle(config))
        for (const op of operations) {
          try {
            await agent.dispatch(op)
          } catch (e) {
            console.warn('Operation dispatch warning:', e)
          }
        }
        finalContent = adapter.getRawContent()
      }

      const isDocumentTarget =
        resolution.targetMode === 'template' ||
        resolution.targetMode === 'plan' ||
        resolution.targetMode === 'report' ||
        detectedIntent === 'template_mutation' ||
        detectedIntent === 'generic_plan' ||
        detectedIntent === 'generic_report'

      const extractedArtifacts = extractFinalArtifacts(
        res.artifacts,
        finalContent,
        config,
        templateContent,
        isDocumentTarget,
      )

      const reconciliation = reconcileGeneratedArtifacts({
        extractedArtifacts,
        convArtifacts: (targetConv?.artifacts || []) as Artifact[],
        activeArtifact,
        finalContent,
        resolution,
        config,
      })
      if (reconciliation.activateArtifactId) opts.onSetActiveArtifactId(reconciliation.activateArtifactId)
      opts.onDocHistoryReset(reconciliation.historyResetContent)

      const bubbleContent = resolveAssistantBubbleText(
        res.assistant_message,
        finalContent,
        resolution.targetMode,
        detectedIntent,
        resolveDocTitle(config),
      )

      const assistantMessage: ChatPersistMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: bubbleContent,
        timestamp: formatNowTime(),
      }

      opts.onUpdateConversation(
        {
          messages: [...updatedMsgs, assistantMessage],
          artifacts: reconciliation.updatedArtifacts as DocumentArtifact[],
          documentContent: finalContent,
          activeArtifactId: reconciliation.targetArtifactId || undefined,
        },
        targetConvId,
      )

      opts.onSetDocPanelCollapsed(false)
    } catch (err) {
      console.error('Error in agentic pipeline:', err)
      const { displayMsg, isAuthError, errorCategory } = classifyAgenticError(err)

      const failureMessage: ChatPersistMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: displayMsg,
        timestamp: formatNowTime(),
      }

      opts.onUpdateConversation(
        {
          messages: [...updatedMsgs, failureMessage],
        },
        targetConvId,
      )

      opts.onError?.(displayMsg, isAuthError, errorCategory)
    } finally {
      this._isGenerating.set(false)
      this._generatingConversationId.set(null)
      this._streamingText.set('')
      opts.onScrollToBottom()
    }
  }
}
