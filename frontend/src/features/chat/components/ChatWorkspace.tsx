import type { FormEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { UniverAdapter } from '../../document/agent/adapters/UniverAdapter'
import { DocumentAgent } from '../../document/agent/core/DocumentAgent'
import type { AgenticGenerationConfig } from '../hooks/useAgenticGeneration'
import { useDocumentHistory } from '../../document/hooks/useDocumentHistory'
import { useCorporateTemplate } from '../../../features/settings'
import {
  useChatPersistence,
  type DocumentArtifact,
} from '../hooks/useChatPersistence'
import { ChatHistorySidebar } from './ChatHistorySidebar'
import { useAuth } from '../../../context/AuthContext'
import { ArtifactsStudio } from '../../document/components/ArtifactsStudio'
import { useArtifacts } from '../hooks/useArtifacts'
import { useAgenticGeneration } from '../hooks/useAgenticGeneration'
import { useToast } from '../../../context/ToastContext'
import { PageHeader } from '../../../components/common'
import type { EphemeralAttachmentDoc } from '../api/docAgentApi'

import { featuresApi } from '../../../api/modules/features'
import { type AIPromptTemplate, type AIRubric } from '../../../api/client'
import { userApi } from '../../../api/modules/user'
import { FEATURE_METAS } from '../../settings/components/prompts_rubrics/types'
import { useCorporateTemplatesList } from '../hooks/useCorporateTemplatesList'
import { useChatAttachments } from '../hooks/useChatAttachments'
import { ChatMessageList } from './ChatMessageList'
import { ChatInputBar } from './ChatInputBar'

export const CHAT_SOURCE_OPTIONS = [
  { id: 'knowledge', label: 'Biblioteca' },
  { id: 'jira', label: 'Jira' },
  { id: 'github', label: 'GitHub' },
]

export const DEFAULT_CHAT_CONFIG: AgenticGenerationConfig & {
  slug: string
  title: string
  subtitle: string
  placeholder: string
  defaultTemplate: string
  defaultSources: string[]
} = {
  slug: 'chat',
  title: 'Chat Asistente',
  subtitle: 'Conversa, adjunta contexto o especificaciones y genera entregables con IA en tiempo real.',
  uploadTags: 'chat_doc',
  placeholder: 'Escribe tu petición o usa /...',
  defaultTemplate: `# Documento de Trabajo y Requerimientos

## 1. Información General
- **Fecha:** {{FECHA}}
- **Responsables:** {{RESPONSABLES}}

## 2. Contexto y Objetivos
{{OBJETIVOS}}

## 3. Especificaciones y Solución Propuesta
{{SOLUCIÓN}}

## 4. Criterios de Aceptación y Pruebas
- Validación funcional y de negocio.`,
  defaultSources: ['knowledge'],
  docxTitle: 'Documento de Trabajo',
  defaultExtension: 'docx',
}

interface ChatWorkspaceProps {
  config?: AgenticGenerationConfig & {
    slug?: string
    title?: string
    subtitle?: string
    placeholder?: string
    defaultTemplate?: string
    defaultSources?: string[]
  }
  eyebrow?: string
}

export const ChatWorkspace = ({
  config = DEFAULT_CHAT_CONFIG,
  eyebrow = 'ASISTENTE VIRTUAL',
}: ChatWorkspaceProps) => {
  const effectiveConfig = useMemo(() => ({
    ...DEFAULT_CHAT_CONFIG,
    ...config,
  }), [config])
  const { user } = useAuth()
  const { toast } = useToast()
  const chatBottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch dynamic corporate template or fallback
  const { templateContent } = useCorporateTemplate(effectiveConfig.slug, effectiveConfig.defaultTemplate)

  // Engine & Agent instances
  const adapter = useMemo(() => new UniverAdapter('document'), [])
  const agent = useMemo(() => new DocumentAgent(adapter), [adapter])

  // Chat persistence
  const {
    conversations,
    activeConversation,
    activeConversationId,
    createConversation,
    updateConversation,
    renameConversation,
    deleteConversation,
    switchConversation,
  } = useChatPersistence(effectiveConfig.slug, user?.id)

  // UI state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [docPanelCollapsed, setDocPanelCollapsed] = useState(true)
  const [draft, setDraft] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // Integrations sources
  const availableIntegrations = useMemo(
    () => CHAT_SOURCE_OPTIONS.filter((opt) => opt.id !== 'knowledge'),
    [],
  )
  const [sources, setSources] = useState<string[]>(
    effectiveConfig.defaultSources || ['knowledge', ...availableIntegrations.map((i) => i.id)],
  )
  const [integrationsFlyoutOpen, setIntegrationsFlyoutOpen] = useState(false)

  // Ephemeral chat attachments hook
  const {
    uploadedDocs,
    uploading,
    attachedImages,
    handlePickFiles,
    handleRemoveUploaded,
    handleRemoveImage,
    resetAttachments,
  } = useChatAttachments(fileInputRef)

  // Corporate templates list hook
  const {
    corporateTemplates,
    visibleCorporateTemplates,
    selectedTemplate,
    selectedTemplateId,
    setSelectedTemplateId,
    templateMenuOpen,
    setTemplateMenuOpen,
    handleTemplateListScroll,
  } = useCorporateTemplatesList()

  const [availablePrompts, setAvailablePrompts] = useState<AIPromptTemplate[]>([])
  const [availableRubrics, setAvailableRubrics] = useState<AIRubric[]>([])
  const [rubricMenuOpen, setRubricMenuOpen] = useState(false)
  const [activeRole, setActiveRole] = useState('funcional')
  const [plusMenuOpen, setPlusMenuOpen] = useState(false)
  const [searchParams] = useSearchParams()
  const [selectedFeatures, setSelectedFeatures] = useState<Array<{ id: string; label: string }>>([])

  useEffect(() => {
    const skillParam = searchParams.get('skill') || searchParams.get('rubric')
    if (skillParam) {
      const meta = FEATURE_METAS.find((item) => item.id === skillParam)
      const label = (meta?.title || skillParam).replace(/\s*\(\/[^)]+\)/, '')
      setSelectedFeatures((prev) => {
        if (prev.some((s) => s.id === skillParam)) return prev
        return [...prev, { id: skillParam, label }]
      })
      textareaRef.current?.focus()
    }
  }, [searchParams])

  useEffect(() => {
    let isMounted = true
    if (!user?.id) return () => {
      isMounted = false
    }

    setActiveRole((user?.role || 'funcional').toLowerCase())
    void userApi.getUserProfile()
      .then((profile) => {
        if (isMounted && profile.user_role) setActiveRole(profile.user_role.toLowerCase())
      })
      .catch(() => undefined)

    void Promise.allSettled([featuresApi.getAiPrompts(), featuresApi.getAiRubrics()])
      .then(([promptsResult, rubricsResult]) => {
        if (!isMounted) return
        const promptsRes = promptsResult.status === 'fulfilled' ? promptsResult.value : null
        const rubricsRes = rubricsResult.status === 'fulfilled' ? rubricsResult.value : null
        if (promptsRes) {
          setAvailablePrompts(promptsRes.prompts || [])
        }
        if (rubricsRes) {
          setAvailableRubrics(rubricsRes.rubrics || [])
        }
      })
    return () => {
      isMounted = false
    }
  }, [user?.id, user?.role])

  const roleFeatureFilter = useMemo(() => {
    const role = activeRole.toLowerCase()
    if (role === 'admin') return null

    return role === 'qa'
      ? new Set(FEATURE_METAS.filter((meta) => meta.category === 'qa').map((meta) => meta.id))
      : role === 'pm'
        ? new Set(FEATURE_METAS.filter((meta) => meta.category === 'product').map((meta) => meta.id))
        : new Set([
            'mejoras_doc',
            'inventario_doc',
            'levantamiento_doc',
            'generic_report',
            ...FEATURE_METAS.filter((meta) => meta.tag === 'transcript_summary').map((meta) => meta.id),
          ])
  }, [activeRole])

  const visiblePrompts = useMemo(
    () => roleFeatureFilter ? availablePrompts.filter((prompt) => roleFeatureFilter.has(prompt.feature)) : availablePrompts,
    [availablePrompts, roleFeatureFilter],
  )
  const visibleRubrics = useMemo(
    () => roleFeatureFilter ? availableRubrics.filter((rubric) => roleFeatureFilter.has(rubric.feature)) : availableRubrics,
    [availableRubrics, roleFeatureFilter],
  )
  const visiblePromptFeatures = useMemo(() => {
    const features = new Set([
      ...visiblePrompts.map((prompt) => prompt.feature),
      ...visibleRubrics.map((rubric) => rubric.feature),
    ])
    return Array.from(features).sort()
  }, [visiblePrompts, visibleRubrics])

  // Dynamic prompt textarea height & expansion (capped at 40% max of chat container height)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const focusEditorEnd = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.focus()
      const len = textareaRef.current.value.length
      textareaRef.current.setSelectionRange(len, len)
    }
  }, [])

  const BASE_TEXTAREA_HEIGHT = 28
  const MAX_PANEL_PERCENT_HEIGHT = 230

  const [textareaHeight, setTextareaHeight] = useState<number>(BASE_TEXTAREA_HEIGHT)
  const [isMaximized, setIsMaximized] = useState<boolean>(false)
  const [userResizedHeight, setUserResizedHeight] = useState<number | null>(null)

  const adjustTextareaHeight = useCallback(() => {
    if (!textareaRef.current) return
    if (isMaximized) {
      setTextareaHeight(MAX_PANEL_PERCENT_HEIGHT)
      return
    }
    if (userResizedHeight !== null) {
      setTextareaHeight(userResizedHeight)
      return
    }
    const currentVal = textareaRef.current.value
    if (!currentVal || currentVal.trim() === '') {
      setTextareaHeight(BASE_TEXTAREA_HEIGHT)
      return
    }
    textareaRef.current.style.height = 'auto'
    const scrollH = textareaRef.current.scrollHeight
    const lineCount = currentVal.split('\n').length

    if (lineCount > 1 || scrollH > 40) {
      setTextareaHeight(
        Math.min(MAX_PANEL_PERCENT_HEIGHT, scrollH + 4),
      )
    } else {
      setTextareaHeight(BASE_TEXTAREA_HEIGHT)
    }
  }, [isMaximized, userResizedHeight])

  useEffect(() => {
    adjustTextareaHeight()
  }, [draft, adjustTextareaHeight])

  const toggleMaximize = () => {
    if (isMaximized) {
      setIsMaximized(false)
      setUserResizedHeight(null)
    } else {
      setIsMaximized(true)
      setUserResizedHeight(MAX_PANEL_PERCENT_HEIGHT)
      setTextareaHeight(MAX_PANEL_PERCENT_HEIGHT)
    }
  }

  // Current conversation messages
  const messages = activeConversation?.messages ?? []

  // Artifacts management hook
  const {
    artifacts,
    activeArtifact,
    activeArtifactId,
    setActiveArtifactId,
    createArtifact: handleCreateArtifact,
    deleteArtifact: handleDeleteArtifact,
    renameArtifact: handleRenameArtifact,
    updateArtifactContent: handleUpdateArtifactContent,
  } = useArtifacts({
    conversationArtifacts: activeConversation?.artifacts ?? [],
    onUpdateConversation: updateConversation,
    currentConversationId: activeConversationId,
  })

  // Document undo/redo history for active artifact content
  const docHistory = useDocumentHistory(activeArtifact?.content || '')

  // Sync active artifact selection
  useEffect(() => {
    if (artifacts.length > 0) {
      if (!activeArtifactId || !artifacts.some((a) => a.id === activeArtifactId)) {
        setActiveArtifactId(artifacts[0].id)
      }
    } else {
      setActiveArtifactId(null)
      setDocPanelCollapsed(true)
    }
  }, [artifacts, activeArtifactId, setActiveArtifactId])

  // Reset history when switching artifact or conversation
  useEffect(() => {
    docHistory.resetHistory(activeArtifact?.content || '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeArtifactId, activeConversationId])

  // Autosave debounce for active artifact explicitly scoped to target conversation
  useEffect(() => {
    if (!docHistory.isDirty || !activeArtifact || !activeConversationId) return
    const targetConvId = activeConversationId
    const targetArtifactId = activeArtifact.id
    const timer = setTimeout(() => {
      setIsSaving(true)
      const updatedList = artifacts.map((a) =>
        a.id === targetArtifactId
          ? { ...a, content: docHistory.content, updatedAt: 'Hace un momento' }
          : a,
      )
      updateConversation(
        {
          artifacts: updatedList as DocumentArtifact[],
          documentContent: docHistory.content,
        },
        targetConvId,
      )
      docHistory.markSaved()
      setTimeout(() => setIsSaving(false), 300)
    }, 1500)
    return () => clearTimeout(timer)
  }, [docHistory.content, docHistory.isDirty, activeArtifact, artifacts, activeConversationId, updateConversation, docHistory])

  // Flush dirty state before switching conversation without changing lastInteraction
  const handleSwitchConversation = useCallback(
    (newId: string) => {
      if (docHistory.isDirty && activeArtifact && activeConversationId) {
        const updatedList = artifacts.map((a) =>
          a.id === activeArtifact.id
            ? { ...a, content: docHistory.content, updatedAt: 'Hace un momento' }
            : a,
        )
        updateConversation(
          {
            artifacts: updatedList as DocumentArtifact[],
            documentContent: docHistory.content,
          },
          activeConversationId,
        )
        docHistory.markSaved()
      }
      switchConversation(newId)
    },
    [docHistory, activeArtifact, activeConversationId, artifacts, updateConversation, switchConversation],
  )

  // Flush dirty state before creating a new conversation
  const handleCreateNewConversation = useCallback(() => {
    if (docHistory.isDirty && activeArtifact && activeConversationId) {
      const updatedList = artifacts.map((a) =>
        a.id === activeArtifact.id
          ? { ...a, content: docHistory.content, updatedAt: 'Hace un momento' }
          : a,
      )
      updateConversation(
        {
          artifacts: updatedList as DocumentArtifact[],
          documentContent: docHistory.content,
        },
        activeConversationId,
      )
      docHistory.markSaved()
    }
    createConversation('Nueva conversación')
  }, [docHistory, activeArtifact, activeConversationId, artifacts, updateConversation, createConversation])

  const scrollToBottom = useCallback(() => {
    setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
  }, [])

  const toggleSource = (srcId: string) => {
    setSources((prev) =>
      prev.includes(srcId) ? prev.filter((s) => s !== srcId) : [...prev, srcId],
    )
  }

  const integrationIds = availableIntegrations.map((i) => i.id)
  const isIntegrationsActive = sources.filter((s) => integrationIds.includes(s)).length > 0

  const toggleAllIntegrations = () => {
    if (isIntegrationsActive) {
      setSources((prev) => prev.filter((s) => !integrationIds.includes(s)))
    } else {
      setSources((prev) => Array.from(new Set([...prev, ...integrationIds])))
    }
  }

  // Agentic generation cycle hook
  const {
    isGenerating,
    generatingConversationId,
    streamingText,
    runState,
    handleCancelRun,
    handleSendMessage,
  } = useAgenticGeneration({
    config,
    templateContent: selectedTemplateId ? templateContent : '',
    templateId: selectedTemplateId,
    sources,
    activeConversation,
    activeArtifact,
    activeArtifactId,
    artifacts,
    docHistoryContent: docHistory.content,
    adapter,
    agent,
    onUpdateConversation: updateConversation,
    onSetActiveArtifactId: setActiveArtifactId,
    onDocHistoryPush: docHistory.pushContent,
    onDocHistoryReset: docHistory.resetHistory,
    onSetDocPanelCollapsed: setDocPanelCollapsed,
    onScrollToBottom: scrollToBottom,
    createConversation,
    renameConversation,
    onResetPromptInputs: () => {
      setDraft('')
      setSelectedFeatures([])
      resetAttachments()
      setRubricMenuOpen(false)
      setUserResizedHeight(null)
      setIsMaximized(false)
      setTextareaHeight(BASE_TEXTAREA_HEIGHT)
    },
    onError: (errMsg, isAuthError, errorCategory) => {
      let title = 'Error del Modelo LLM'
      if (errorCategory === 'gpu') {
        title = 'Memoria de GPU Insuficiente'
      } else if (isAuthError || errorCategory === 'auth') {
        title = 'Error de Autenticación'
      } else if (errorCategory === 'context') {
        title = 'Contexto Insuficiente'
      } else if (errorCategory === 'rate_limit') {
        title = 'Límite de Tokens'
      }
      toast.error(errMsg, title, 10000)
    },
  })

  const isCurrentChatGenerating = isGenerating && generatingConversationId === activeConversationId

  const handleSubmitForm = (e?: FormEvent) => {
    e?.preventDefault()
    const effectiveDraft = draft.trim()
    const commandsPrefix = selectedFeatures.map((s) => `/${s.id}`).join(' ')
    const query = commandsPrefix
      ? `${commandsPrefix}${effectiveDraft ? ` ${effectiveDraft}` : ''}`
      : effectiveDraft
    if ((!query.trim() && attachedImages.length === 0 && uploadedDocs.length === 0) || isGenerating) return
    const imagesToSend = [...attachedImages]
    const docsToSend = [...uploadedDocs]
    resetAttachments()
    setSelectedFeatures([])
    setDraft('')
    setTextareaHeight(BASE_TEXTAREA_HEIGHT)
    void handleSendMessage(query, imagesToSend, docsToSend)
  }

  return (
    <div className="space-y-6 font-sans">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.docx,.doc,.txt,.xlsx"
        multiple
        className="hidden"
        onChange={(e) => handlePickFiles(e.target.files)}
      />

      <PageHeader
        eyebrow={eyebrow}
        title={effectiveConfig.title}
        subtitle={effectiveConfig.subtitle}
      />

      <div className="flex h-[calc(100vh-235px)] min-h-[580px] w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <ChatHistorySidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          generatingConversationId={generatingConversationId}
          isCollapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          onSelectConversation={handleSwitchConversation}
          onCreateConversation={handleCreateNewConversation}
          onDeleteConversation={deleteConversation}
          onRenameConversation={renameConversation}
        />

        <div
          className={`flex flex-col overflow-hidden bg-white border-r border-slate-200 shadow-xs transition-all duration-200 ${
            docPanelCollapsed
              ? 'flex-1'
              : 'w-full max-w-[480px] xl:max-w-[540px] shrink-0'
          }`}
        >
          <ChatMessageList
            messages={messages}
            title={effectiveConfig.title}
            subtitle={effectiveConfig.subtitle}
            isCurrentChatGenerating={isCurrentChatGenerating}
            streamingText={streamingText}
            runState={runState}
            chatBottomRef={chatBottomRef}
            onCancelRun={() => void handleCancelRun()}
          />

          <ChatInputBar
            draft={draft}
            setDraft={setDraft}
            textareaRef={textareaRef}
            fileInputRef={fileInputRef}
            textareaHeight={textareaHeight}
            isMaximized={isMaximized}
            toggleMaximize={toggleMaximize}
            isGenerating={isGenerating}
            placeholder={effectiveConfig.placeholder}
            selectedFeatures={selectedFeatures}
            setSelectedFeatures={setSelectedFeatures}
            rubricMenuOpen={rubricMenuOpen}
            setRubricMenuOpen={setRubricMenuOpen}
            visiblePromptFeatures={visiblePromptFeatures}
            attachedImages={attachedImages}
            uploadedDocs={uploadedDocs}
            uploading={uploading}
            onRemoveImage={handleRemoveImage}
            onRemoveUploaded={handleRemoveUploaded}
            selectedTemplate={selectedTemplate}
            selectedTemplateId={selectedTemplateId}
            setSelectedTemplateId={setSelectedTemplateId}
            corporateTemplates={corporateTemplates}
            visibleCorporateTemplates={visibleCorporateTemplates}
            templateMenuOpen={templateMenuOpen}
            setTemplateMenuOpen={setTemplateMenuOpen}
            onTemplateListScroll={handleTemplateListScroll}
            sources={sources}
            availableIntegrations={availableIntegrations}
            toggleSource={toggleSource}
            toggleAllIntegrations={toggleAllIntegrations}
            onSubmitForm={handleSubmitForm}
            onCancelRun={() => void handleCancelRun()}
            focusEditorEnd={focusEditorEnd}
            plusMenuOpen={plusMenuOpen}
            setPlusMenuOpen={setPlusMenuOpen}
            integrationsFlyoutOpen={integrationsFlyoutOpen}
            setIntegrationsFlyoutOpen={setIntegrationsFlyoutOpen}
          />
        </div>

        <ArtifactsStudio
          adapter={adapter}
          artifacts={artifacts}
          activeArtifactId={activeArtifactId}
          isCollapsed={docPanelCollapsed}
          onToggleCollapse={() => setDocPanelCollapsed(!docPanelCollapsed)}
          onSelectArtifact={(id) => setActiveArtifactId(id)}
          onCreateArtifact={handleCreateArtifact}
          onDeleteArtifact={handleDeleteArtifact}
          onRenameArtifact={handleRenameArtifact}
          onUpdateArtifactContent={handleUpdateArtifactContent}
          canUndo={docHistory.canUndo}
          canRedo={docHistory.canRedo}
          onUndo={docHistory.undo}
          onRedo={docHistory.redo}
          isDirty={docHistory.isDirty}
          isSaving={isSaving}
          onRegenerate={() => {
            const userMsgs = (activeConversation?.messages ?? []).filter((m) => m.role === 'user')
            const lastUserMsg = userMsgs[userMsgs.length - 1]

            const msgWithAttachments = (lastUserMsg?.attachments && lastUserMsg.attachments.length > 0)
              ? lastUserMsg
              : [...userMsgs].reverse().find((m) => m.attachments && m.attachments.length > 0)

            const attachedImagesList = (msgWithAttachments?.attachments || [])
              .filter((att) => att.type === 'image' && att.dataUrl)
              .map((att) => ({ name: att.name, dataUrl: att.dataUrl!, size: att.size }))

            const attachedDocsList: EphemeralAttachmentDoc[] = (msgWithAttachments?.attachments || [])
              .filter((att) => att.type === 'file')
              .map((att) => ({
                id: att.id,
                filename: att.name,
                content: att.content || '',
                char_count: att.size,
              }))

            const queryToUse = (
              activeArtifact
                ? `Regenera y completa rigurosamente el documento "${activeArtifact.title}" con todas sus secciones, tablas y especificaciones técnicas a partir del contexto provisto.`
                : (lastUserMsg?.content || 'Regenera el documento funcional.')
            )

            void handleSendMessage(queryToUse, attachedImagesList, attachedDocsList)
          }}
        />
      </div>
    </div>
  )
}

export default ChatWorkspace
