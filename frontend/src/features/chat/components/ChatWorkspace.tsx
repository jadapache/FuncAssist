import type { FormEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Sparkles, ChevronDown, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { UniverAdapter } from '../../document/agent/adapters/UniverAdapter'
import { DocumentAgent } from '../../document/agent/core/DocumentAgent'
import type { AgenticGenerationConfig } from '../hooks/useAgenticGeneration'
import { useDocumentHistory } from '../../document/hooks/useDocumentHistory'
import { useCorporateTemplate } from '../../../features/settings'
import { useChat } from '../../../context/ChatContext'
import { useSidebar } from '../../../context/SidebarContext'
import { useAuth } from '../../../context/AuthContext'
import { useArtifacts } from '../hooks/useArtifacts'
import { useAgenticGeneration } from '../hooks/useAgenticGeneration'
import { useToast } from '../../../context/ToastContext'
import { featuresApi } from '../../../api/modules/features'
import { aiSettingsApi } from '../../../features/settings/api/aiSettingsApi'
import { type AIPromptTemplate, type AIRubric } from '../../../api/client'
import { userApi } from '../../../api/modules/user'
import { FEATURE_METAS } from '../../settings/components/prompts_rubrics/types'
import { useCorporateTemplatesList } from '../hooks/useCorporateTemplatesList'
import { useChatAttachments } from '../hooks/useChatAttachments'
import { ChatMessageList } from './ChatMessageList'
import { ChatInputBar } from './ChatInputBar'
import { ArtifactModal } from './ArtifactModal'
import type { Artifact } from '../../../types/artifacts'

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
  title: 'Chat',
  subtitle: 'Conversa, adjunta contexto o especificaciones y genera entregables con IA en tiempo real.',
  uploadTags: 'chat_doc',
  placeholder: 'Escribe tu mensaje...',
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
}

export const ChatWorkspace = ({
  config = DEFAULT_CHAT_CONFIG,
}: ChatWorkspaceProps) => {
  const { isCollapsed, toggleSidebar } = useSidebar()
  const effectiveConfig = useMemo(
    () => ({
      ...DEFAULT_CHAT_CONFIG,
      ...config,
    }),
    [config],
  )
  const { user } = useAuth()
  const { toast } = useToast()
  const chatBottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch dynamic corporate template or fallback
  const { templateContent } = useCorporateTemplate(
    effectiveConfig.slug,
    effectiveConfig.defaultTemplate,
  )

  // Engine & Agent instances
  const adapter = useMemo(() => new UniverAdapter('document'), [])
  const agent = useMemo(() => new DocumentAgent(adapter), [adapter])

  // Chat state from shared ChatContext
  const {
    activeConversation,
    activeConversationId,
    createConversation,
    updateConversation,
    renameConversation,
  } = useChat()

  // Artifacts state management
  const [modalArtifact, setModalArtifact] = useState<Artifact | null>(null)
  const [draft, setDraft] = useState('')

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
  const [activeModelName, setActiveModelName] = useState<string>('FuncAssist (LLM)')
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
    void userApi
      .getUserProfile()
      .then((profile) => {
        if (isMounted && profile.user_role) setActiveRole(profile.user_role.toLowerCase())
      })
      .catch(() => undefined)

    void Promise.allSettled([
      featuresApi.getAiPrompts(),
      featuresApi.getAiRubrics(),
      aiSettingsApi.getAiSettings(),
    ]).then(([promptsResult, rubricsResult, aiSettingsResult]) => {
      if (!isMounted) return
      const promptsRes = promptsResult.status === 'fulfilled' ? promptsResult.value : null
      const rubricsRes = rubricsResult.status === 'fulfilled' ? rubricsResult.value : null
      const aiSettingsRes = aiSettingsResult.status === 'fulfilled' ? aiSettingsResult.value : null

      if (promptsRes) {
        setAvailablePrompts(promptsRes.prompts || [])
      }
      if (rubricsRes) {
        setAvailableRubrics(rubricsRes.rubrics || [])
      }
      if (aiSettingsRes?.model) {
        setActiveModelName(aiSettingsRes.model)
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
    () => (roleFeatureFilter ? availablePrompts.filter((p) => roleFeatureFilter.has(p.feature)) : availablePrompts),
    [availablePrompts, roleFeatureFilter],
  )
  const visibleRubrics = useMemo(
    () => (roleFeatureFilter ? availableRubrics.filter((r) => roleFeatureFilter.has(r.feature)) : availableRubrics),
    [availableRubrics, roleFeatureFilter],
  )
  const visiblePromptFeatures = useMemo(() => {
    const features = new Set([
      ...visiblePrompts.map((p) => p.feature),
      ...visibleRubrics.map((r) => r.feature),
    ])
    return Array.from(features).sort()
  }, [visiblePrompts, visibleRubrics])

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
  const [isMaximized, setIsMaximized] = useState(false)
  const [userResizedHeight, setUserResizedHeight] = useState<number | null>(null)

  const toggleMaximize = useCallback(() => {
    if (isMaximized) {
      setIsMaximized(false)
      setTextareaHeight(userResizedHeight || BASE_TEXTAREA_HEIGHT)
    } else {
      setIsMaximized(true)
      setTextareaHeight(MAX_PANEL_PERCENT_HEIGHT)
    }
  }, [isMaximized, userResizedHeight])

  const {
    artifacts,
    activeArtifact,
    activeArtifactId,
    setActiveArtifactId,
    deleteArtifact,
    updateArtifactContent,
  } = useArtifacts({
    conversationArtifacts: (activeConversation?.artifacts || []) as any,
    currentConversationId: activeConversationId,
    onUpdateConversation: updateConversation,
  })

  const messages = activeConversation?.messages ?? []

  const docHistory = useDocumentHistory(activeArtifact?.content || '')

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
    onSetDocPanelCollapsed: () => {},
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

  const isCurrentChatGenerating =
    isGenerating && generatingConversationId === activeConversationId

  const handleSubmitForm = (e?: FormEvent) => {
    e?.preventDefault()
    const effectiveDraft = draft.trim()
    const commandsPrefix = selectedFeatures.map((s) => `/${s.id}`).join(' ')
    const query = commandsPrefix
      ? `${commandsPrefix}${effectiveDraft ? ` ${effectiveDraft}` : ''}`
      : effectiveDraft
    if ((!query.trim() && attachedImages.length === 0 && uploadedDocs.length === 0) || isGenerating)
      return
    const imagesToSend = [...attachedImages]
    const docsToSend = [...uploadedDocs]
    resetAttachments()
    setSelectedFeatures([])
    setDraft('')
    setTextareaHeight(BASE_TEXTAREA_HEIGHT)
    void handleSendMessage(query, imagesToSend, docsToSend)
  }

  const handleRetryMessage = (content: string, attachments?: typeof messages[number]['attachments']) => {
    if (isGenerating) return

    const imagesToSend: Array<{ name: string; dataUrl: string; size?: number }> = []
    const docsToSend: Array<{ id: string; filename: string; content: string; char_count: number }> = []

    if (attachments) {
      for (const att of attachments) {
        if (att.type === 'image' && att.dataUrl) {
          imagesToSend.push({ name: att.name, dataUrl: att.dataUrl, size: att.size })
        } else if (att.type === 'file' && att.content) {
          docsToSend.push({
            id: att.id,
            filename: att.name,
            content: att.content,
            char_count: att.size || att.content.length,
          })
        }
      }
    }

    void handleSendMessage(content, imagesToSend, docsToSend)
  }

  return (
    <div className="flex flex-col h-full w-full bg-white font-sans overflow-hidden">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.docx,.doc,.txt,.xlsx"
        multiple
        className="hidden"
        onChange={(e) => handlePickFiles(e.target.files)}
      />

      {/* Top Header Row with Chat Title, Sidebar Toggle, and Model Selector */}
      <header className="flex h-14 items-center justify-between px-6 border-b border-slate-200/80 bg-white shrink-0 z-10">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleSidebar}
            className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition shadow-2xs cursor-pointer shrink-0"
            title={isCollapsed ? 'Expandir menú lateral' : 'Colapsar menú lateral'}
            aria-label={isCollapsed ? 'Expandir menú lateral' : 'Colapsar menú lateral'}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
          <span className="text-slate-300 font-light text-sm" aria-hidden>
            |
          </span>
          <h1 className="text-sm md:text-base font-bold text-slate-800 tracking-tight">Chat</h1>
        </div>

        {/* Model Selector Dropdown Pill */}
        <div className="relative">
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-800 shadow-2xs hover:bg-slate-50 transition cursor-pointer">
            <Sparkles className="h-4 w-4 text-[#002777]" />
            <span className="max-w-[200px] truncate" title={activeModelName}>
              {activeModelName}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </div>
        </div>
      </header>

      {/* Main Centered Chat Container */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden w-full max-w-4xl mx-auto px-4 md:px-6">
        <ChatMessageList
          messages={messages}
          artifacts={artifacts}
          title={effectiveConfig.title}
          subtitle={effectiveConfig.subtitle}
          isCurrentChatGenerating={isCurrentChatGenerating}
          streamingText={streamingText}
          runState={runState}
          chatBottomRef={chatBottomRef}
          onCancelRun={() => void handleCancelRun()}
          onOpenArtifact={(art) => setModalArtifact(art)}
          onRetryMessage={handleRetryMessage}
        />

        <div className="pb-4 pt-2">
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
      </div>

      {/* Artifact Detailed View Modal */}
      {modalArtifact && (
        <ArtifactModal
          artifact={modalArtifact}
          adapter={adapter}
          canUndo={docHistory.canUndo}
          canRedo={docHistory.canRedo}
          isDirty={docHistory.isDirty}
          onUndo={docHistory.undo}
          onRedo={docHistory.redo}
          onClose={() => setModalArtifact(null)}
          onDelete={(id) => {
            deleteArtifact(id)
            setModalArtifact(null)
          }}
          onUpdateContent={(id, newContent) => {
            updateArtifactContent(id, newContent)
            setModalArtifact((prev) => (prev ? { ...prev, content: newContent } : null))
          }}
        />
      )}
    </div>
  )
}

export default ChatWorkspace
