/**
 * Hook que encapsula el ciclo completo de generación agentic:
 * prompt del usuario → llamada al backend → parsing de artefactos → actualización de estado.
 */

import { useCallback, useRef, useState } from 'react'
import { api, type KnowledgeDocument } from '../../../api/client'
import { generateArtifactSubtitle, parseMultipleArtifacts } from '../../../utils/artifactSplitter'
import type { ThinkingStep, ChatPersistMessage, DocumentArtifact, ChatConversation } from './useChatPersistence'
import type { Artifact } from '../../../types/artifacts'
import type { FuncionalFeatureConfig } from '../../../features/funcional'
import type { CanonicalDocumentOperation } from '../../../features/document/agent/core/types'
import type { DocumentAgent } from '../../../features/document/agent/core/DocumentAgent'
import type { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'

interface UseAgenticGenerationOptions {
  config: FuncionalFeatureConfig
  templateContent: string
  sources: string[]
  uploaded: KnowledgeDocument[]
  activeConversation: ChatConversation | null
  activeArtifact: Artifact | null
  activeArtifactId: string | null
  artifacts: Artifact[]
  docHistoryContent: string
  adapter: UniverAdapter
  agent: DocumentAgent
  onUpdateConversation: (updates: Partial<ChatConversation>) => void
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
  liveThinkingSteps: ThinkingStep[]
  handleSendMessage: (query?: string) => Promise<void>
}

export function useAgenticGeneration(opts: UseAgenticGenerationOptions): GenerationResult {
  const [isGenerating, setIsGenerating] = useState(false)
  const [liveThinkingSteps, setLiveThinkingSteps] = useState<ThinkingStep[]>([])
  const liveThinkingStepsRef = useRef<ThinkingStep[]>([])

  const updateLiveThinkingSteps = useCallback(
    (updater: ThinkingStep[] | ((prev: ThinkingStep[]) => ThinkingStep[])) => {
      setLiveThinkingSteps((prev) => {
        const next = typeof updater === 'function' ? updater(prev) : updater
        liveThinkingStepsRef.current = next
        return next
      })
    },
    [],
  )

  const {
    config,
    templateContent,
    sources,
    uploaded,
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
    async (customQuery?: string) => {
      const queryText = (customQuery || '').trim()
      if (!queryText || isGenerating) return

      setIsGenerating(true)
      onResetPromptInputs?.()

      const userMsgId = crypto.randomUUID()
      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

      const userMessage: ChatPersistMessage = {
        id: userMsgId,
        role: 'user',
        content: queryText,
        timestamp: now,
      }

      // Create or title conversation dynamically on first user prompt
      let targetConv = activeConversation
      if (!targetConv) {
        const convTitle = queryText.length > 28 ? `${queryText.slice(0, 28)}...` : queryText
        targetConv = createConversation(convTitle)
      } else if (
        targetConv.messages.length === 0 &&
        (targetConv.name === 'Nueva conversación' || targetConv.name.startsWith('Conversación '))
      ) {
        const convTitle = queryText.length > 28 ? `${queryText.slice(0, 28)}...` : queryText
        renameConversation(targetConv.id, convTitle)
      }

      const currentMsgs = targetConv?.messages ?? []
      const updatedMsgs = [...currentMsgs, userMessage]
      onUpdateConversation({ messages: updatedMsgs })
      onScrollToBottom()

      // Initialize thinking steps
      const steps: ThinkingStep[] = [
        { id: '1', label: '1. Identificando objetivo y entidades de negocio', status: 'in_progress' },
        { id: '2', label: '2. Consultando fuentes de conocimiento activas', status: 'pending' },
        { id: '3', label: '3. Mutando árbol canónico del documento', status: 'pending' },
        { id: '4', label: '4. Verificando plantilla', status: 'pending' },
        { id: '5', label: '5. Renderizando contenido', status: 'pending' },
      ]
      updateLiveThinkingSteps(steps)

      try {
        // Step 1 -> Step 2
        await new Promise((r) => setTimeout(r, 400))
        updateLiveThinkingSteps((prev) =>
          prev.map((s) =>
            s.id === '1'
              ? { ...s, status: 'completed' }
              : s.id === '2'
                ? { ...s, status: 'in_progress' }
                : s,
          ),
        )

        // Run backend Agentic RAG prompt API with live streaming
        const currentDocContent = docHistoryContent || activeArtifact?.content || templateContent || ''
        let latestAccumulatedText = ''

        const res = await api.agenticPromptStream(
          {
            query: queryText,
            current_document: currentDocContent,
            chat_context: currentMsgs.slice(-4).map((m) => `${m.role}: ${m.content}`),
            sources,
            document_ids: uploaded.map((d) => d.id),
          },
          (accumulatedText) => {
            latestAccumulatedText = accumulatedText

            // Update live thinking steps as chunks stream in
            updateLiveThinkingSteps((prev) =>
              prev.map((s) =>
                s.id === '1' || s.id === '2'
                  ? { ...s, status: 'completed' }
                  : s.id === '3' || s.id === '4' || s.id === '5'
                    ? { ...s, status: 'in_progress' }
                    : s,
              ),
            )

            // Parse multi-artifacts dynamically during streaming
            const streamExtracted = parseMultipleArtifacts(
              accumulatedText,
              config.docxTitle || config.title,
              'docx',
              templateContent,
            )

            if (streamExtracted.length > 0) {
              onSetDocPanelCollapsed(false)

              const nowFormatted = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              const baseList = [...artifacts]
              const mergedList: Artifact[] = streamExtracted.map((item, idx) => {
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

              onUpdateConversation({
                artifacts: mergedList as DocumentArtifact[],
                documentContent: streamExtracted[0]?.content || accumulatedText,
              })

              if (streamExtracted[0]?.content) {
                onDocHistoryPush(streamExtracted[0].content)
              }
            }
          },
        )

        const candidateContent = res.document_updates || res.answer || latestAccumulatedText
        if (!candidateContent || !candidateContent.trim()) {
          throw new Error(
            'El modelo no generó contenido para el documento. Verifica la conexión y tu clave de API en Configuración.',
          )
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

        updateLiveThinkingSteps((prev) => prev.map((s) => ({ ...s, status: 'completed' })))

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
            )

        let updatedArtifacts: Artifact[] = [...artifacts]
        let targetArtifactId: string | null = activeArtifactId

        if (extractedArtifacts.length > 1) {
          // Multi-artifact response: create each distinct artifact
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

          updatedArtifacts = [...updatedArtifacts, ...newCreatedItems]
          targetArtifactId = newCreatedItems[0].id
          onSetActiveArtifactId(newCreatedItems[0].id)
          onDocHistoryReset(newCreatedItems[0].content)
        } else if (artifacts.length === 0) {
          // Create first single artifact dynamically
          const newArtId = crypto.randomUUID()
          const newArtifact: Artifact = {
            id: newArtId,
            title: extractedArtifacts[0]?.title || config.docxTitle || config.title,
            subtitle: 'Generado por Asistente IA',
            extension: extractedArtifacts[0]?.extension || 'docx',
            content: finalContent,
            createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            updatedAt: 'Hace un momento',
          }
          updatedArtifacts = [newArtifact]
          targetArtifactId = newArtId
          onSetActiveArtifactId(newArtId)
          onDocHistoryReset(finalContent)
        } else {
          // Update currently active artifact
          const targetId = activeArtifact?.id || artifacts[0].id
          updatedArtifacts = artifacts.map((a) =>
            a.id === targetId ? { ...a, content: finalContent, updatedAt: 'Hace un momento' } : a,
          )
          onDocHistoryPush(finalContent)
        }

        // Formulate a concise chat bubble message for the user
        const isFullDocumentMarkdown =
          (res.answer &&
            (res.answer.startsWith('#') || res.answer.includes('## ') || res.answer.includes('| --- |'))) ||
          (res.document_updates && res.document_updates.length > 150)

        let bubbleContent = res.assistant_message
        if (!bubbleContent || isFullDocumentMarkdown) {
          bubbleContent =
            extractedArtifacts.length > 1
              ? `Se han generado ${extractedArtifacts.length} artefactos de forma independiente y progresiva en tiempo real. Puedes navegar entre ellos, editarlos o descargarlos desde el panel de Artefactos a la derecha.`
              : 'Documento generado exitosamente. Puedes revisarlo, editarlo en directo o descargarlo desde el panel de Artefactos a la derecha.'
        }

        // Save assistant response message with attached thinking steps
        const assistantMessage: ChatPersistMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: bubbleContent,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          thinkingSteps: steps.map((s) => ({ ...s, status: 'completed' })),
        }

        onUpdateConversation({
          messages: [...updatedMsgs, assistantMessage],
          artifacts: updatedArtifacts as DocumentArtifact[],
          documentContent: finalContent,
          activeArtifactId: targetArtifactId || undefined,
        })

        // Expand right Artefactos panel now that LLM document response is ready
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

        // Mark current liveThinkingSteps with failed status
        const currentSteps = liveThinkingStepsRef.current.length > 0 ? liveThinkingStepsRef.current : steps
        const failedSteps: ThinkingStep[] = currentSteps.map((s) => {
          if (s.status === 'in_progress') {
            const stepDetail = isContextMissingError
              ? 'No se encontraron fragmentos relevantes en las fuentes de contexto'
              : errMsg
            return { ...s, status: 'failed', details: stepDetail }
          }
          if (s.status === 'completed') {
            return s
          }
          return { ...s, status: 'failed' }
        })

        let displayMsg = errMsg
        if (isAuthError) {
          displayMsg = `Error: La API key guardada no es válida. Por favor actualízala en Configuración.`
        } else if (isRateLimitError) {
          const limitMatch = errMsg.match(/Limit\s*(\d+)/i)
          const reqMatch = errMsg.match(/Requested\s*(\d+)/i)
          const reqTokens = reqMatch ? reqMatch[1] : 'la cantidad enviada de'
          const limitTokens = limitMatch ? limitMatch[1] : 'el'
          displayMsg = `La solicitud con ${reqTokens} tokens supera el límite de ${limitTokens} tokens de salida para este modelo. Por favor, selecciona un modelo diferente en Configuración.`
        } else if (isContextMissingError) {
          if (/no matching chunks/i.test(errMsg)) {
            displayMsg = `No se tiene información suficiente para responder a esta solicitud.`
          } else if (/no documents uploaded/i.test(errMsg)) {
            displayMsg = `La base de conocimiento no tiene documentos para consultar.`
          } else if (errMsg.startsWith('No se encontró') || errMsg.startsWith('No hay')) {
            displayMsg = errMsg
          } else {
            displayMsg = `No se encontró contexto suficiente para procesar la consulta.`
          }
        } else if (errMsg.startsWith('La solicitud con') || errMsg.startsWith('Hubo un error')) {
          displayMsg = errMsg
        } else {
          displayMsg = `Error al conectar o recibir respuesta del modelo: ${errMsg}`
        }

        const assistantMessage: ChatPersistMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: displayMsg,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          thinkingSteps: failedSteps,
        }

        onUpdateConversation({ messages: [...updatedMsgs, assistantMessage] })
        onError?.(displayMsg, isAuthError, errorCategory)
      } finally {
        setIsGenerating(false)
        updateLiveThinkingSteps([])
      }
    },
    [
      isGenerating,
      activeConversation,
      createConversation,
      renameConversation,
      onUpdateConversation,
      onScrollToBottom,
      docHistoryContent,
      activeArtifact,
      templateContent,
      sources,
      uploaded,
      config,
      adapter,
      agent,
      artifacts,
      activeArtifactId,
      onSetActiveArtifactId,
      onDocHistoryReset,
      onDocHistoryPush,
      onSetDocPanelCollapsed,
      onResetPromptInputs,
      onError,
      updateLiveThinkingSteps,
    ],
  )

  return { isGenerating, liveThinkingSteps, handleSendMessage }
}
