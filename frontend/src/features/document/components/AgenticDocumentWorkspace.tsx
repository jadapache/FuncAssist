import type { FormEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp,
  BookOpen,
  FileText,
  Plus,
  RefreshCw,
  Sparkles,
  X,
  Layers,
  Check,
  ChevronUp,
  Maximize2,
  Minimize2,
} from 'lucide-react'
import { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'
import { DocumentAgent } from '../../../features/document/agent/core/DocumentAgent'
import type { FuncionalFeatureConfig } from '../../../features/funcional'
import { FUNCIONAL_SOURCE_OPTIONS } from '../../../features/funcional'
import { useDocumentHistory } from '../hooks/useDocumentHistory'
import { useCorporateTemplate } from '../../../features/settings'
import {
  useChatPersistence,
  type ChatPersistMessage,
  type DocumentArtifact,
} from '../../../features/document/hooks/useChatPersistence'
import { ChatHistorySidebar } from './ChatHistorySidebar'
import { AgenticThinkingBubble } from './AgenticThinkingBubble'
import { ArtifactsStudio } from './ArtifactsStudio'
import { useArtifacts } from '../hooks/useArtifacts'
import { useAgenticGeneration } from '../hooks/useAgenticGeneration'
import { useToast } from '../../../context/ToastContext'
import { PageHeader } from '../../../components/common'
import { MarkdownMessage } from './MarkdownMessage'
import { docAgentApi, type EphemeralAttachmentDoc } from '../api/docAgentApi'


interface AgenticDocumentWorkspaceProps {
  config: FuncionalFeatureConfig
  eyebrow?: string
}

export const AgenticDocumentWorkspace = ({
  config,
  eyebrow = 'FUNCIONAL TOOLS',
}: AgenticDocumentWorkspaceProps) => {
  const { toast } = useToast()
  const chatBottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch dynamic corporate template or fallback
  const { templateContent } = useCorporateTemplate(config.slug, config.defaultTemplate)

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
  } = useChatPersistence(config.slug)

  // UI state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [docPanelCollapsed, setDocPanelCollapsed] = useState(true)
  const [draft, setDraft] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // Filter available integrations dynamically from FUNCIONAL_SOURCE_OPTIONS
  const availableIntegrations = useMemo(
    () => FUNCIONAL_SOURCE_OPTIONS.filter((opt) => opt.id !== 'knowledge'),
    [],
  )

  const [sources, setSources] = useState<string[]>(
    config.defaultSources || ['knowledge', ...availableIntegrations.map((i) => i.id)],
  )

  // Integrations flyout menu state
  const [integrationsFlyoutOpen, setIntegrationsFlyoutOpen] = useState(false)


  // Ephemeral chat attachments (never stored in knowledge base)
  const [uploadedDocs, setUploadedDocs] = useState<EphemeralAttachmentDoc[]>([])
  const [uploading, setUploading] = useState(false)
  const [attachedImages, setAttachedImages] = useState<
    Array<{ id: string; name: string; dataUrl: string; size: number }>
  >([])

  // Dynamic prompt textarea height & expansion (capped at 40% max of chat container height)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const BASE_TEXTAREA_HEIGHT = 35
  const MAX_PANEL_PERCENT_HEIGHT = 230 // Maximum 40% of chat panel height cap

  const [textareaHeight, setTextareaHeight] = useState<number>(BASE_TEXTAREA_HEIGHT)
  const [isMaximized, setIsMaximized] = useState<boolean>(false)
  const [userResizedHeight, setUserResizedHeight] = useState<number | null>(null)

  // Dynamically calculate and auto-expand height to fit multi-line content smoothly
  const adjustTextareaHeight = useCallback(() => {
    if (userResizedHeight !== null) return

    if (isMaximized) {
      setTextareaHeight(MAX_PANEL_PERCENT_HEIGHT)
      return
    }

    if (!textareaRef.current) return

    if (!draft || draft.trim() === '') {
      setTextareaHeight(BASE_TEXTAREA_HEIGHT)
      return
    }

    textareaRef.current.style.height = 'auto'
    const scrollH = textareaRef.current.scrollHeight
    const lineCount = draft.split('\n').length

    // Auto-expand to fit text smoothly up to 40% max height cap
    if (lineCount > 1 || scrollH > 40) {
      const targetH = Math.max(
        BASE_TEXTAREA_HEIGHT,
        Math.min(MAX_PANEL_PERCENT_HEIGHT, scrollH + 4),
      )
      setTextareaHeight(targetH)
    } else {
      setTextareaHeight(BASE_TEXTAREA_HEIGHT)
    }
  }, [draft, isMaximized, userResizedHeight])

  useEffect(() => {
    adjustTextareaHeight()
  }, [draft, adjustTextareaHeight])

  // Toggle maximize/restore button in top-right corner
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
  const messages: ChatPersistMessage[] = activeConversation?.messages ?? []

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
    if (activeArtifact) {
      docHistory.resetHistory(activeArtifact.content || '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeArtifactId, activeConversationId])

  // Autosave debounce for active artifact
  useEffect(() => {
    if (!docHistory.isDirty || !activeArtifact) return
    const timer = setTimeout(() => {
      setIsSaving(true)
      const updatedList = artifacts.map((a) =>
        a.id === activeArtifact.id
          ? { ...a, content: docHistory.content, updatedAt: 'Hace un momento' }
          : a,
      )
      updateConversation({
        artifacts: updatedList as DocumentArtifact[],
        documentContent: docHistory.content,
      })
      docHistory.markSaved()
      setTimeout(() => setIsSaving(false), 300)
    }, 1500)
    return () => clearTimeout(timer)
  }, [docHistory.content, docHistory.isDirty, activeArtifact, artifacts, updateConversation, docHistory])

  // Scroll chat to bottom
  const scrollToBottom = useCallback(() => {
    setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
  }, [])

  // Upload context document or attach image
  const handlePickFiles = async (picked: FileList | File[] | null) => {
    if (!picked || !picked.length) return
    const files = Array.from(picked)
    const imageFiles = files.filter(
      (f) => f.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name),
    )
    const docFiles = files.filter(
      (f) => !f.type.startsWith('image/') && !/\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name),
    )

    if (imageFiles.length > 0) {
      for (const img of imageFiles) {
        const reader = new FileReader()
        reader.onload = () => {
          if (typeof reader.result === 'string') {
            setAttachedImages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                name: img.name,
                dataUrl: reader.result as string,
                size: img.size,
              },
            ])
          }
        }
        reader.readAsDataURL(img)
      }
    }

    if (docFiles.length > 0) {
      setUploading(true)
      try {
        const parsed = await Promise.all(
          docFiles.map((file) => docAgentApi.parseAttachment(file)),
        )
        setUploadedDocs((prev) => [...prev, ...parsed])
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error al procesar los documentos adjuntos')
      } finally {
        setUploading(false)
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleRemoveUploaded = (id: string) => {
    // Simply detach from prompt input without calling destructive backend delete
    setUploadedDocs((prev) => prev.filter((d) => d.id !== id))
  }

  const toggleSource = (srcId: string) => {
    setSources((prev) =>
      prev.includes(srcId) ? prev.filter((s) => s !== srcId) : [...prev, srcId],
    )
  }

  const isKnowledgeActive = sources.includes('knowledge')
  const integrationIds = availableIntegrations.map((i) => i.id)
  const activeIntegrationsCount = sources.filter((s) => integrationIds.includes(s)).length
  const isIntegrationsActive = activeIntegrationsCount > 0

  const toggleAllIntegrations = () => {
    if (isIntegrationsActive) {
      setSources((prev) => prev.filter((s) => !integrationIds.includes(s)))
    } else {
      setSources((prev) => Array.from(new Set([...prev, ...integrationIds])))
    }
  }

  // Agentic generation cycle hook
  const { isGenerating, streamingText, generationStatus, handleSendMessage } = useAgenticGeneration({
    config,
    templateContent,
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
      setUserResizedHeight(null)
      setIsMaximized(false)
      setTextareaHeight(BASE_TEXTAREA_HEIGHT)
    },
    onError: (errMsg, isAuthError, errorCategory) => {
      let title = 'Error del Modelo LLM'
      if (isAuthError || errorCategory === 'auth') {
        title = 'Error de Autenticación'
      } else if (errorCategory === 'context') {
        title = 'Contexto Insuficiente'
      } else if (errorCategory === 'rate_limit') {
        title = 'Límite de Tokens'
      }
      toast.error(errMsg, title, 10000)
    },
  })

  const handleSubmitForm = (e: FormEvent) => {
    e.preventDefault()
    if ((!draft.trim() && attachedImages.length === 0 && uploadedDocs.length === 0) || isGenerating) return
    const imagesToSend = [...attachedImages]
    const docsToSend = [...uploadedDocs]
    setAttachedImages([])
    setUploadedDocs([])
    void handleSendMessage(draft, imagesToSend, docsToSend)
  }

  return (
    <div className="space-y-6 font-sans">
      {/* File Upload Hidden Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.docx,.doc,.txt,.xlsx"
        multiple
        className="hidden"
        onChange={(e) => handlePickFiles(e.target.files)}
      />

      {/* Top Page Title Banner Header (Standardized) */}
      <PageHeader
        eyebrow={eyebrow}
        title={config.title}
        subtitle={config.subtitle}
      />

      {/* Main Workspace Card Container (Encloses Sidebar + Chat Panel + Artefactos Studio) */}
      <div className="flex h-[calc(100vh-235px)] min-h-[580px] w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {/* Left Chat History Collapsible Sidebar */}
        <ChatHistorySidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          isCollapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          onSelectConversation={switchConversation}
          onCreateConversation={() => createConversation('Nueva conversación')}
          onDeleteConversation={deleteConversation}
          onRenameConversation={renameConversation}
        />

        {/* Center Chat Panel */}
        <div
          className={`flex flex-col overflow-hidden bg-white border-r border-slate-200 shadow-xs transition-all duration-200 ${docPanelCollapsed
              ? 'flex-1'
              : 'w-full max-w-[480px] xl:max-w-[540px] shrink-0'
            }`}
        >
          {/* Chat Thread Messages */}
          <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3 max-w-md mx-auto">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-[#002777] border border-blue-100 shadow-xs">
                  <Sparkles className="h-6 w-6" />
                </div>
                <div className="space-y-1">
                  <h2 className="text-base font-bold text-slate-900">{config.title}</h2>
                  <p className="text-xs text-slate-500 leading-relaxed">{config.subtitle}</p>
                </div>
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`flex gap-3 text-xs ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl p-3.5 space-y-1.5 ${m.role === 'user'
                        ? 'bg-[#002777] text-white rounded-br-none shadow-sm'
                        : 'bg-slate-100 text-slate-800 border border-slate-200/80 rounded-bl-none'
                        }`}
                    >
                      <div className="flex items-center justify-between gap-4 text-[10px] opacity-70 font-medium">
                        <span>{m.role === 'user' ? 'Tú' : 'Asistente IA'}</span>
                        <span>{m.timestamp}</span>
                      </div>
                      {m.role === 'user' ? (
                        <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                      ) : (
                        <MarkdownMessage content={m.content} />
                      )}

                      {/* Attached images and documents inside message bubble */}
                      {m.attachments && m.attachments.length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {m.attachments.map((att) =>
                            att.type === 'image' && att.dataUrl ? (
                              <a
                                key={att.id}
                                href={att.dataUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block"
                              >
                                <img
                                  src={att.dataUrl}
                                  alt={att.name}
                                  className="h-14 w-14 object-cover rounded-xl border border-white/20 shadow-2xs hover:opacity-90 transition"
                                />
                              </a>
                            ) : (
                              <span
                                key={att.id}
                                className="inline-flex items-center gap-1.5 text-[11px] bg-white/15 px-2.5 py-1 rounded-xl border border-white/20 text-white shadow-2xs font-medium"
                              >
                                <FileText className="h-3.5 w-3.5 text-blue-200" />
                                <span className="truncate max-w-[200px]">{att.name}</span>
                              </span>
                            ),
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Live streaming assistant bubble while processing */}
                {isGenerating && (
                  <div className="flex gap-3 justify-start animate-in fade-in duration-150">
                    <div className="max-w-[85%] rounded-2xl p-3.5 bg-slate-100 text-slate-800 border border-slate-200 rounded-bl-none space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-4 text-[10px] opacity-70 font-medium">
                        <span>Asistente IA</span>
                      </div>
                      <AgenticThinkingBubble
                        status={generationStatus}
                        isProcessing={!streamingText}
                      />
                      {streamingText && (
                        <MarkdownMessage content={streamingText} />
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={chatBottomRef} />
          </div>

          {/* Chat Input Bar */}
          <div className="p-4 border-t border-slate-200/80 bg-white shrink-0 space-y-2">
            {/* Quick Slash Commands bar */}
            <div className="flex items-center gap-1.5 px-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Atajos:</span>
              <button
                type="button"
                onClick={() => {
                  setDraft((d) => (d.startsWith('/plan') ? d : `/plan ${d}`.trim()))
                  textareaRef.current?.focus()
                }}
                className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-lg bg-slate-100 hover:bg-blue-50 hover:text-[#002777] text-slate-600 border border-slate-200/80 transition cursor-pointer"
              >
                <Sparkles className="h-2.5 w-2.5" />
                /plan
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft((d) => (d.startsWith('/informe') ? d : `/informe ${d}`.trim()))
                  textareaRef.current?.focus()
                }}
                className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-lg bg-slate-100 hover:bg-blue-50 hover:text-[#002777] text-slate-600 border border-slate-200/80 transition cursor-pointer"
              >
                <FileText className="h-2.5 w-2.5" />
                /informe
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft((d) => (d.startsWith('/plantilla') ? d : `/plantilla ${d}`.trim()))
                  textareaRef.current?.focus()
                }}
                className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-lg bg-slate-100 hover:bg-blue-50 hover:text-[#002777] text-slate-600 border border-slate-200/80 transition cursor-pointer"
              >
                /plantilla
              </button>
            </div>

            <form onSubmit={handleSubmitForm} className="relative">
              {/* Input Box Card */}
              <div className="relative rounded-2xl border border-slate-200 bg-slate-50/50 p-3 shadow-2xs focus-within:bg-white focus-within:border-slate-300 focus-within:ring-2 focus-within:ring-blue-100/80 transition space-y-2.5">
                {/* Top-right corner control: Maximize/Minimize toggle (capped at 40% max height) */}
                <div className="absolute top-2.5 right-2.5 flex items-center gap-1 z-10">
                  <button
                    type="button"
                    onClick={toggleMaximize}
                    className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition cursor-pointer"
                    title={isMaximized ? "Restaurar tamaño del campo" : "Expandir campo de chat (máx. 40%)"}
                  >
                    {isMaximized ? (
                      <Minimize2 className="h-3.5 w-3.5" />
                    ) : (
                      <Maximize2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>

                <textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onPaste={(e) => {
                    const items = e.clipboardData?.items
                    if (items) {
                      const pastedFiles: File[] = []
                      for (let i = 0; i < items.length; i++) {
                        if (items[i].type.startsWith('image/')) {
                          const file = items[i].getAsFile()
                          if (file) pastedFiles.push(file)
                        }
                      }
                      if (pastedFiles.length > 0) {
                        void handlePickFiles(pastedFiles)
                      }
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSubmitForm(e)
                    }
                  }}
                  placeholder={config.placeholder || 'Escribe tu petición, consulta o usa /plan...'}
                  disabled={isGenerating}
                  style={{ height: `${textareaHeight}px` }}
                  className="w-full bg-transparent px-1 pr-16 text-xs text-slate-800 outline-none resize-none placeholder:text-slate-400 disabled:opacity-60 font-sans overflow-y-auto scrollbar-thin transition-[height] duration-150 ease-out leading-normal"
                />

                {/* Attached Images Thumbnail Row */}
                {attachedImages.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 px-1 py-1 border-t border-slate-200/40">
                    {attachedImages.map((img) => (
                      <div
                        key={img.id}
                        className="relative group h-12 w-12 rounded-xl overflow-hidden border border-slate-200 bg-slate-100 shadow-2xs"
                      >
                        <img src={img.dataUrl} alt={img.name} className="h-full w-full object-cover" />
                        <button
                          type="button"
                          onClick={() => setAttachedImages((prev) => prev.filter((i) => i.id !== img.id))}
                          className="absolute top-0.5 right-0.5 p-0.5 bg-black/60 hover:bg-black/80 text-white rounded-full transition cursor-pointer"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Attached Files Inline Badge Row (Inside prompt card) */}
                {uploadedDocs.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 px-1 py-1 border-t border-slate-200/40">
                    {uploadedDocs.map((doc) => (
                      <span
                        key={doc.id}
                        className="inline-flex items-center gap-1.5 bg-blue-50 text-[#002777] border border-blue-200/80 text-xs font-medium px-2.5 py-1 rounded-xl shrink-0 shadow-2xs"
                      >
                        <FileText className="h-3.5 w-3.5 text-[#002777]" />
                        <span className="truncate max-w-[180px]">{doc.filename}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveUploaded(doc.id)}
                          className="hover:text-red-600 transition ml-0.5 cursor-pointer"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                {/* Bottom Actions Row: Attachment (+) on left, Pills + Send on right */}
                <div className="flex items-center justify-between gap-2 pt-1 border-t border-slate-200/60">
                  {/* Left: Attachment button (+) */}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className="h-7 w-7 rounded-full bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 flex items-center justify-center transition shrink-0 cursor-pointer shadow-2xs"
                    title="Adjuntar archivo de contexto"
                  >
                    {uploading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-4 w-4" />}
                  </button>

                  {/* Right: Sources Pills & Send Button */}
                  <div className="flex items-center gap-2 relative">
                    {/* Biblioteca Pill */}
                    <button
                      type="button"
                      onClick={() => toggleSource('knowledge')}
                      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-xl border transition cursor-pointer ${isKnowledgeActive
                        ? 'bg-[#002777] text-white border-[#002777] shadow-2xs'
                        : 'bg-white text-slate-600 border-slate-200 hover:text-slate-800'
                        }`}
                    >
                      <BookOpen className="h-3.5 w-3.5" />
                      <span>Biblioteca</span>
                    </button>

                    {/* Integraciones Pill with Hover/Click Flyout */}
                    <div
                      className="relative"
                      onMouseEnter={() => setIntegrationsFlyoutOpen(true)}
                      onMouseLeave={() => setIntegrationsFlyoutOpen(false)}
                    >
                      <button
                        type="button"
                        onClick={toggleAllIntegrations}
                        className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-xl border transition cursor-pointer ${isIntegrationsActive
                          ? 'bg-[#002777] text-white border-[#002777] shadow-2xs'
                          : 'bg-white text-slate-600 border-slate-200 hover:text-slate-800'
                          }`}
                      >
                        <Layers className="h-3.5 w-3.5" />
                        <span>Integraciones</span>
                        {activeIntegrationsCount > 0 && (
                          <span className="h-4 w-4 rounded-full bg-white text-[#002777] text-[10px] font-bold flex items-center justify-center ml-0.5">
                            {activeIntegrationsCount}
                          </span>
                        )}
                        <ChevronUp className="h-3 w-3 opacity-60" />
                      </button>

                      {/* Floating Flyout Menu on Hover/Click */}
                      {integrationsFlyoutOpen && (
                        <div className="absolute right-0 bottom-9 w-48 rounded-2xl bg-white border border-slate-200 shadow-xl p-2 z-50 text-xs space-y-1">
                          <div className="px-2 py-1 border-b border-slate-100 font-bold text-slate-800 text-[11px]">
                            Integraciones habilitadas
                          </div>
                          {availableIntegrations.map((opt) => {
                            const active = sources.includes(opt.id)
                            return (
                              <button
                                key={opt.id}
                                type="button"
                                onClick={() => toggleSource(opt.id)}
                                className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg hover:bg-blue-50/70 text-slate-700 transition cursor-pointer"
                              >
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold text-slate-900">{opt.label}</span>
                                </div>
                                {active && <Check className="h-3.5 w-3.5 text-[#002777]" />}
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </div>

                    {/* Send Button (↑) */}
                    <button
                      type="submit"
                      disabled={isGenerating || !draft.trim()}
                      className="h-8 w-8 rounded-full flex items-center justify-center transition shrink-0 shadow-xs ml-1 bg-[#002777] text-white hover:bg-[#003399] disabled:opacity-30 disabled:hover:bg-[#002777] cursor-pointer"
                      title={isGenerating ? 'Generando respuesta...' : 'Enviar consulta'}
                    >
                      {isGenerating ? (
                        <RefreshCw className="h-4 w-4 animate-spin text-white" />
                      ) : (
                        <ArrowUp className="h-4 w-4 stroke-[2.5]" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* Right Panel: Studio / Artefactos (Claude/NotebookLM Style) */}
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
            const lastUserMsg = (activeConversation?.messages ?? [])
              .filter((m) => m.role === 'user')
              .pop()
            if (lastUserMsg) {
              handleSendMessage(lastUserMsg.content)
            }
          }}
        />
      </div>
    </div>
  )
}
