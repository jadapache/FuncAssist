/**
 * Hook que encapsula el ciclo completo de generación agentic:
 * prompt del usuario → llamada al backend → streaming en vivo en el chat → actualización de estado.
 */

import { useCallback, useState } from 'react'
import { generateArtifactSubtitle, parseMultipleArtifacts, parseStreamForChatAndArtifacts } from '../../../utils/artifactSplitter'
import type { EphemeralAttachmentDoc } from '../api/docAgentApi'
import { useAgentRun } from './useAgentRun'
import type { AgentRunState } from '../types/agentEvents'
import type { ChatPersistMessage, DocumentArtifact, ChatConversation, ChatAttachment } from './useChatPersistence'
import type { Artifact } from '../../../types/artifacts'
import type { FuncionalFeatureConfig } from '../../../features/funcional'
import type { CanonicalDocumentOperation } from '../../../features/document/agent/core/types'
import type { DocumentAgent } from '../../../features/document/agent/core/DocumentAgent'
import type { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'

interface UseAgenticGenerationOptions {
  config: FuncionalFeatureConfig
  templateContent: string
  sources: string[]
  activeConversation: ChatConversation | null
  activeArtifact: Artifact | null
  activeArtifactId: string | null
  artifacts: Artifact[]
  docHistoryContent: string
  adapter: UniverAdapter
  agent: DocumentAgent
  onUpdateConversation: (updates: Partial<ChatConversation>, targetId?: string) => void
  onSetActiveArtifactId: (id: string) => void
  onDocHistoryPush: (content: string) => void
  onDocHistoryReset: (content: string) => void
  onSetDocPanelCollapsed: (v: boolean) => void
  onScrollToBottom: () => void
  createConversation: (name?: string) => ChatConversation
  renameConversation: (id: string, name: string) => void
  onResetPromptInputs?: () => void
  onError?: (
    errorMessage: string,
    isAuthError: boolean,
    errorCategory?: 'auth' | 'rate_limit' | 'context' | 'general',
  ) => void
}

export interface GenerationResult {
  isGenerating: boolean
  generatingConversationId: string | null
  streamingText: string
  generationStatus: string
  liveThinkingSteps: unknown[]
  runState: AgentRunState
  handleCancelRun: () => Promise<void>
  handleSendMessage: (
    query?: string,
    attachedImages?: Array<{ name: string; dataUrl: string; size?: number }>,
    attachedDocs?: EphemeralAttachmentDoc[],
  ) => Promise<void>
}

interface IntentResolution {
  commandSlug: string | null
  cleanQuery: string
  targetFeature: string
  targetMode: string
  initialStatus: string
  isChatOnly: boolean
}

function resolveIntentAndStatus(
  queryText: string,
  defaultFeature: string,
): IntentResolution {
  const pLower = queryText.toLowerCase()
  const isQuestion =
    pLower.startsWith('¿') ||
    pLower.startsWith('que ') ||
    pLower.startsWith('qué ') ||
    pLower.startsWith('como ') ||
    pLower.startsWith('cómo ') ||
    pLower.startsWith('cual ') ||
    pLower.startsWith('cuál ') ||
    pLower.startsWith('por que') ||
    pLower.startsWith('por qué') ||
    pLower.startsWith('explica') ||
    pLower.includes('?')

  const commandMatch = queryText.match(/^\/([a-zA-Z0-9_-]+)(?:\s+(.*))?$/s)
  const commandSlug = commandMatch ? commandMatch[1].toLowerCase() : null
  const cleanQuery = commandMatch && commandMatch[2] ? commandMatch[2].trim() : queryText

  if (commandSlug) {
    if (commandSlug === 'plan') {
      return {
        commandSlug,
        cleanQuery,
        targetFeature: 'generic_plan',
        targetMode: 'plan',
        initialStatus: 'Generando plan...',
        isChatOnly: false,
      }
    }
    if (commandSlug === 'informe' || commandSlug === 'report') {
      return {
        commandSlug,
        cleanQuery,
        targetFeature: 'generic_report',
        targetMode: 'report',
        initialStatus: 'Elaborando informe...',
        isChatOnly: false,
      }
    }
    if (commandSlug === 'plantilla') {
      return {
        commandSlug,
        cleanQuery,
        targetFeature: defaultFeature,
        targetMode: 'template',
        initialStatus: 'Estructurando documento...',
        isChatOnly: false,
      }
    }
    return {
      commandSlug,
      cleanQuery,
      targetFeature: commandSlug,
      targetMode: commandSlug,
      initialStatus: `Ejecutando /${commandSlug}...`,
      isChatOnly: false,
    }
  }

  if (isQuestion) {
    return {
      commandSlug: null,
      cleanQuery,
      targetFeature: defaultFeature,
      targetMode: 'chat',
      initialStatus: 'Pensando...',
      isChatOnly: true,
    }
  }

  if (pLower.includes('plan de') || pLower.includes('genera un plan') || pLower.includes('crea un plan')) {
    return {
      commandSlug: 'plan',
      cleanQuery,
      targetFeature: 'generic_plan',
      targetMode: 'plan',
      initialStatus: 'Generando plan...',
      isChatOnly: false,
    }
  }

  if (pLower.includes('informe') || pLower.includes('reporte') || pLower.includes('resumen ejecutivo')) {
    return {
      commandSlug: 'informe',
      cleanQuery,
      targetFeature: 'generic_report',
      targetMode: 'report',
      initialStatus: 'Elaborando informe...',
      isChatOnly: false,
    }
  }

  if (pLower.includes('completa la plantilla') || pLower.includes('genera el documento')) {
    return {
      commandSlug: 'plantilla',
      cleanQuery,
      targetFeature: defaultFeature,
      targetMode: 'template',
      initialStatus: 'Estructurando documento...',
      isChatOnly: false,
    }
  }

  return {
    commandSlug: null,
    cleanQuery,
    targetFeature: defaultFeature,
    targetMode: 'auto',
    initialStatus: 'Pensando...',
    isChatOnly: false,
  }
}

function resolveAssistantBubbleText(
  resMsg: string | undefined,
  finalContent: string,
  targetMode: string,
  detectedIntent: string,
  docTitle: string,
): string {
  if (resMsg && !resMsg.includes('<artifact') && resMsg !== finalContent) {
    return resMsg.replace(/<\/?chat>/gi, '').trim()
  }

  const parsed = parseStreamForChatAndArtifacts(finalContent, docTitle)
  if (parsed.chatText && !parsed.chatText.includes('<artifact') && parsed.chatText !== finalContent) {
    return parsed.chatText
  }

  if (targetMode === 'plan' || detectedIntent === 'generic_plan') {
    return 'He elaborado el plan solicitado. Puedes revisarlo, editarlo y descargarlo en el panel de Artefactos.'
  }
  if (targetMode === 'report' || detectedIntent === 'generic_report') {
    return 'He estructurado el informe solicitado con las evidencias y hallazgos. Puedes consultarlo en el panel de Artefactos.'
  }
  return 'He generado el documento correspondiente en el panel de artefactos.'
}

export function useAgenticGeneration(opts: UseAgenticGenerationOptions): GenerationResult {
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatingConversationId, setGeneratingConversationId] = useState<string | null>(null)
  const [streamingText, setStreamingText] = useState('')
  const [generationStatus, setGenerationStatus] = useState('Pensando...')
  const { runState, executeRun, cancelRun } = useAgentRun()

  const {
    config,
    templateContent,
    sources,
    activeConversation,
    activeArtifact,
    activeArtifactId,
    artifacts,
    docHistoryContent,
    adapter,
    agent,
    onUpdateConversation,
    onSetActiveArtifactId,
    onDocHistoryPush,
    onDocHistoryReset,
    onSetDocPanelCollapsed,
    onScrollToBottom,
    createConversation,
    renameConversation,
    onResetPromptInputs,
    onError,
  } = opts

  const handleSendMessage = useCallback(
    async (
      customQuery?: string,
      attachedImages?: Array<{ name: string; dataUrl: string; size?: number }>,
      attachedDocs?: EphemeralAttachmentDoc[],
    ) => {
      const queryText = (customQuery || '').trim()
      if ((!queryText && (!attachedImages || attachedImages.length === 0) && (!attachedDocs || attachedDocs.length === 0)) || isGenerating) {
        return
      }

      setIsGenerating(true)
      setStreamingText('')
      onResetPromptInputs?.()

      const userMsgId = crypto.randomUUID()
      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

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
        targetConv = createConversation(convTitle)
      } else if (
        targetConv.messages.length === 0 &&
        (targetConv.name === 'Nueva conversación' || targetConv.name.startsWith('Conversación '))
      ) {
        const convTitle = titleSeed.length > 28 ? `${titleSeed.slice(0, 28)}...` : titleSeed
        renameConversation(targetConv.id, convTitle)
      }

      const targetConvId = targetConv.id
      setGeneratingConversationId(targetConvId)
      const currentMsgs = targetConv?.messages ?? []
      const updatedMsgs = [...currentMsgs, userMessage]
      onUpdateConversation({ messages: updatedMsgs }, targetConvId)
      onScrollToBottom()

      const defaultFeature = config.uploadTags || config.slug
      const resolution = resolveIntentAndStatus(queryText, defaultFeature)
      setGenerationStatus(resolution.initialStatus)

      try {
        const currentDocContent = docHistoryContent || activeArtifact?.content || templateContent || ''
        let latestAccumulatedText = ''
        let liveIntent = resolution.targetFeature

        const res = await executeRun(
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
            chat_context: currentMsgs.slice(-4).map((m) => `${m.role}: ${m.content}`),
            sources,
            conversation_id: targetConvId,
          },
          (accumulatedText) => {
            latestAccumulatedText = accumulatedText

            const parsedStream = parseStreamForChatAndArtifacts(
              accumulatedText,
              config.docxTitle || config.title,
              'docx',
              templateContent,
            )

            if (!parsedStream.isConversational && parsedStream.artifacts.length > 0) {
              setStreamingText(parsedStream.chatText)
              onSetDocPanelCollapsed(false)

              const nowFormatted = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              const baseList = [...((targetConv?.artifacts || []) as Artifact[])]
              const mergedList: Artifact[] = parsedStream.artifacts.map((item, idx) => {
                const existing = baseList.find((a) => a.title.toLowerCase() === item.title.toLowerCase())
                return {
                  id: existing ? existing.id : `art-stream-${idx}`,
                  title: item.title,
                  subtitle: generateArtifactSubtitle(item.content) || `Artefacto #${idx + 1} - Generado por IA`,
                  extension: item.extension,
                  content: item.content,
                  createdAt: existing?.createdAt || nowFormatted,
                  updatedAt: 'Generando...',
                }
              })

              onUpdateConversation(
                {
                  artifacts: mergedList as DocumentArtifact[],
                  documentContent: parsedStream.artifacts[0]?.content || accumulatedText,
                },
                targetConvId,
              )

              if (parsedStream.artifacts[0]?.content) {
                onDocHistoryPush(parsedStream.artifacts[0].content)
              }
            } else {
              setStreamingText(parsedStream.chatText || accumulatedText)
            }
          },
          (intent) => {
            liveIntent = intent
            if (intent === 'generic_plan') setGenerationStatus('Generando plan...')
            else if (intent === 'generic_report') setGenerationStatus('Elaborando informe...')
            else if (intent === 'template_mutation') setGenerationStatus('Mutando plantilla...')
            else setGenerationStatus('Pensando...')
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
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          }

          onUpdateConversation(
            {
              messages: [...updatedMsgs, assistantMessage],
            },
            targetConvId,
          )
          setStreamingText('')
          setIsGenerating(false)
          return
        }

        let finalContent = candidateContent
        const rawOps = (res.operations ?? res.planned_operations ?? []) as unknown[]
        const operations = rawOps.filter(
          (op): op is CanonicalDocumentOperation =>
            typeof op === 'object' && op !== null && 'operation' in op,
        )

        if (operations.length > 0) {
          await adapter.loadTemplate(currentDocContent, 'document', config.docxTitle || config.title)
          for (const op of operations) {
            try {
              await agent.dispatch(op)
            } catch (e) {
              console.warn('Operation dispatch warning:', e)
            }
          }
          finalContent = adapter.getRawContent()
        }

        const backendArtifacts = res.artifacts
        const extractedArtifacts =
          backendArtifacts && backendArtifacts.length > 0
            ? backendArtifacts.map((a) => ({
              title: a.title,
              extension: (a.extension as 'docx' | 'xlsx' | 'txt') || config.defaultExtension || 'docx',
              content: a.content,
            }))
            : parseMultipleArtifacts(
              finalContent,
              config.docxTitle || config.title,
              config.defaultExtension || 'docx',
              templateContent,
              false,
            )

        const convArtifacts = (targetConv?.artifacts || []) as Artifact[]
        let updatedArtifacts: Artifact[] = [...convArtifacts]
        let targetArtifactId: string | null = activeArtifactId

        if (extractedArtifacts.length > 1) {
          const nowFormatted = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          const newCreatedItems: Artifact[] = extractedArtifacts.map((extracted, idx) => ({
            id: crypto.randomUUID(),
            title: extracted.title,
            subtitle: generateArtifactSubtitle(extracted.content) || `Artefacto #${idx + 1} - Generado por IA`,
            extension: extracted.extension,
            content: extracted.content,
            createdAt: nowFormatted,
            updatedAt: 'Hace un momento',
          }))

          updatedArtifacts = [...convArtifacts, ...newCreatedItems]
          targetArtifactId = newCreatedItems[0].id
          onSetActiveArtifactId(newCreatedItems[0].id)
          onDocHistoryReset(newCreatedItems[0].content)
        } else if (extractedArtifacts.length === 1 || resolution.targetMode === 'plan' || resolution.targetMode === 'report' || convArtifacts.length === 0) {
          const newArtId = crypto.randomUUID()
          const artifactTitle =
            extractedArtifacts[0]?.title ||
            (resolution.commandSlug
              ? `${resolution.commandSlug.toUpperCase()}: ${resolution.cleanQuery.slice(0, 30)}`
              : config.docxTitle || config.title)

          const newArtifact: Artifact = {
            id: newArtId,
            title: artifactTitle,
            subtitle: generateArtifactSubtitle(extractedArtifacts[0]?.content || finalContent) || 'Documento generado por IA',
            extension: extractedArtifacts[0]?.extension || config.defaultExtension || 'docx',
            content: extractedArtifacts[0]?.content || finalContent,
            createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            updatedAt: 'Hace un momento',
          }
          updatedArtifacts = [...convArtifacts, newArtifact]
          targetArtifactId = newArtId
          onSetActiveArtifactId(newArtId)
          onDocHistoryReset(newArtifact.content)
        } else {
          const targetId = activeArtifact?.id || convArtifacts[0]?.id
          updatedArtifacts = convArtifacts.map((a) =>
            a.id === targetId ? { ...a, content: finalContent, updatedAt: 'Hace un momento' } : a,
          )
          onDocHistoryPush(finalContent)
        }

        const bubbleContent = resolveAssistantBubbleText(
          res.assistant_message,
          finalContent,
          resolution.targetMode,
          detectedIntent,
          config.docxTitle || config.title,
        )

        const assistantMessage: ChatPersistMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: bubbleContent,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }

        onUpdateConversation(
          {
            messages: [...updatedMsgs, assistantMessage],
            artifacts: updatedArtifacts as DocumentArtifact[],
            documentContent: finalContent,
            activeArtifactId: targetArtifactId || undefined,
          },
          targetConvId,
        )

        onSetDocPanelCollapsed(false)
      } catch (err) {
        console.error('Error in agentic pipeline:', err)
        const errMsg = err instanceof Error ? err.message : 'Error desconocido'

        const isAuthError =
          /api\s*key|autenticaci[oó]n|authentication|unauthorized|401|forbidden|403|invalid_api_key/i.test(errMsg)

        const isRateLimitError =
          /reduce max_tokens|OTPM|output tokens per minute|RateLimitError/i.test(errMsg)

        const isContextMissingError =
          /not found in connected sources|no matching chunks|no documents uploaded|sin coincidencias en el contexto|no se encontr[oó] informaci[oó]n/i.test(errMsg)

        let errorCategory: 'auth' | 'rate_limit' | 'context' | 'general' = 'general'
        if (isAuthError) errorCategory = 'auth'
        else if (isRateLimitError) errorCategory = 'rate_limit'
        else if (isContextMissingError) errorCategory = 'context'

        let displayMsg = errMsg
        if (isAuthError) {
          displayMsg = 'Error: La API key guardada no es válida. Por favor actualízala en Configuración.'
        } else if (isRateLimitError) {
          displayMsg = 'La solicitud supera el límite de tokens de salida para este modelo.'
        } else if (isContextMissingError) {
          displayMsg = 'No se encontró contexto suficiente en las fuentes para procesar la consulta.'
        }

        const failureMessage: ChatPersistMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: displayMsg,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }

        onUpdateConversation(
          {
            messages: [...updatedMsgs, failureMessage],
          },
          targetConvId,
        )

        onError?.(displayMsg, isAuthError, errorCategory)
      } finally {
        setIsGenerating(false)
        setGeneratingConversationId(null)
        setStreamingText('')
        onScrollToBottom()
      }
    },
    [
      isGenerating,
      onResetPromptInputs,
      activeConversation,
      onUpdateConversation,
      onScrollToBottom,
      docHistoryContent,
      activeArtifact,
      templateContent,
      config,
      sources,
      adapter,
      agent,
      artifacts,
      activeArtifactId,
      onSetActiveArtifactId,
      onDocHistoryReset,
      onDocHistoryPush,
      onSetDocPanelCollapsed,
      createConversation,
      renameConversation,
      onError,
    ],
  )

  return {
    isGenerating,
    generatingConversationId,
    streamingText,
    generationStatus: runState.activeStatusText || generationStatus,
    liveThinkingSteps: runState.steps,
    runState,
    handleCancelRun: cancelRun,
    handleSendMessage,
  }
}

