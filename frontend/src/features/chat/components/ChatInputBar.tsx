import type { FormEvent, RefObject, UIEvent } from 'react'
import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  Layers,
  Maximize2,
  Minimize2,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
  X,
} from 'lucide-react'
import { VoiceInput } from '../../transcription/components/VoiceInput'
import type { EphemeralAttachmentDoc } from '../api/docAgentApi'
import type { CorporateTemplate } from '../../../api/client'
import { FEATURE_METAS } from '../../settings/components/prompts_rubrics/types'
import type { AttachedImage } from '../hooks/useChatAttachments'

interface ChatInputBarProps {
  draft: string
  setDraft: (val: string | ((prev: string) => string)) => void
  textareaRef: RefObject<HTMLTextAreaElement | null>
  fileInputRef: RefObject<HTMLInputElement | null>
  textareaHeight: number
  isMaximized: boolean
  toggleMaximize: () => void
  isGenerating: boolean
  placeholder: string
  selectedFeatures: Array<{ id: string; label: string }>
  setSelectedFeatures: (val: Array<{ id: string; label: string }> | ((prev: Array<{ id: string; label: string }>) => Array<{ id: string; label: string }>)) => void
  rubricMenuOpen: boolean
  setRubricMenuOpen: (open: boolean) => void
  visiblePromptFeatures: string[]
  // Attachments
  attachedImages: AttachedImage[]
  uploadedDocs: EphemeralAttachmentDoc[]
  uploading: boolean
  onRemoveImage: (id: string) => void
  onRemoveUploaded: (id: string) => void
  // Templates
  selectedTemplate: CorporateTemplate | null
  selectedTemplateId: string | null
  setSelectedTemplateId: (id: string | null) => void
  corporateTemplates: CorporateTemplate[]
  visibleCorporateTemplates: CorporateTemplate[]
  templateMenuOpen: boolean
  setTemplateMenuOpen: (open: boolean | ((prev: boolean) => boolean)) => void
  onTemplateListScroll: (event: UIEvent<HTMLDivElement>) => void
  // Sources
  sources: string[]
  availableIntegrations: Array<{ id: string; label: string }>
  toggleSource: (srcId: string) => void
  toggleAllIntegrations: () => void
  // Submission
  onSubmitForm: (e?: FormEvent) => void
  onCancelRun: () => void
  focusEditorEnd: () => void
  plusMenuOpen: boolean
  setPlusMenuOpen: (open: boolean | ((prev: boolean) => boolean)) => void
  integrationsFlyoutOpen: boolean
  setIntegrationsFlyoutOpen: (open: boolean) => void
}

export const ChatInputBar = ({
  draft,
  setDraft,
  textareaRef,
  fileInputRef,
  textareaHeight,
  isMaximized,
  toggleMaximize,
  isGenerating,
  placeholder,
  selectedFeatures,
  setSelectedFeatures,
  rubricMenuOpen,
  setRubricMenuOpen,
  visiblePromptFeatures,
  attachedImages,
  uploadedDocs,
  uploading,
  onRemoveImage,
  onRemoveUploaded,
  selectedTemplate,
  selectedTemplateId,
  setSelectedTemplateId,
  corporateTemplates,
  visibleCorporateTemplates,
  templateMenuOpen,
  setTemplateMenuOpen,
  onTemplateListScroll,
  sources,
  availableIntegrations,
  toggleSource,
  toggleAllIntegrations,
  onSubmitForm,
  onCancelRun,
  focusEditorEnd,
  plusMenuOpen,
  setPlusMenuOpen,
  integrationsFlyoutOpen,
  setIntegrationsFlyoutOpen,
}: ChatInputBarProps) => {
  const isKnowledgeActive = sources.includes('knowledge')
  const integrationIds = availableIntegrations.map((i) => i.id)
  const activeIntegrationsCount = sources.filter((s) => integrationIds.includes(s)).length
  const isIntegrationsActive = activeIntegrationsCount > 0

  return (
    <div className="p-4 border-t border-slate-200/80 bg-white shrink-0 space-y-2">
      {selectedTemplate && (
        <div className="flex items-center gap-2 px-1 py-1 text-[11px] border-b border-slate-100">
          <FileText className="h-3.5 w-3.5 text-[#002777] shrink-0" />
          <span className="font-semibold text-slate-500">Formato:</span>
          <span className="truncate font-semibold text-[#002777]" title={selectedTemplate.title}>
            {selectedTemplate.title}
          </span>
          <button
            type="button"
            onClick={() => setSelectedTemplateId(null)}
            className="ml-auto rounded-md p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition cursor-pointer"
            title="Quitar formato corporativo"
            aria-label="Quitar formato corporativo"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <form onSubmit={onSubmitForm} className="relative">
        <div className="relative rounded-2xl border border-slate-200 bg-slate-50/50 p-3 shadow-2xs focus-within:bg-white focus-within:border-slate-300 focus-within:ring-2 focus-within:ring-blue-100/80 transition space-y-2.5">
          <div className="absolute top-2.5 right-2.5 flex items-center gap-1 z-10">
            <button
              type="button"
              onClick={toggleMaximize}
              className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition cursor-pointer"
              title={isMaximized ? 'Restaurar tamaño del campo' : 'Expandir campo de chat (máx. 40%)'}
            >
              {isMaximized ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
          </div>

          {/* Attached Previews */}
          {attachedImages.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pb-1 border-b border-slate-200/50">
              {attachedImages.map((img) => (
                <div
                  key={img.id}
                  className="relative group h-12 w-12 rounded-xl overflow-hidden border border-slate-200 bg-slate-100 shadow-2xs"
                >
                  <img src={img.dataUrl} alt={img.name} className="h-full w-full object-cover" />
                  <button
                    type="button"
                    onClick={() => onRemoveImage(img.id)}
                    className="absolute top-0.5 right-0.5 p-0.5 bg-black/60 hover:bg-black/80 text-white rounded-full transition cursor-pointer"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Attached Files Badges */}
          {uploadedDocs.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pb-1 border-b border-slate-200/50">
              {uploadedDocs.map((doc) => (
                <span
                  key={doc.id}
                  className="inline-flex items-center gap-1.5 bg-blue-50 text-[#002777] border border-blue-200/80 text-xs font-medium px-2.5 py-1 rounded-xl shrink-0 shadow-2xs"
                >
                  <FileText className="h-3.5 w-3.5 text-[#002777]" />
                  <span className="truncate max-w-[180px]">{doc.filename}</span>
                  <button
                    type="button"
                    onClick={() => onRemoveUploaded(doc.id)}
                    className="hover:text-red-600 transition ml-0.5 cursor-pointer"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Textarea Row with Inline Selected Skill Chips */}
          <div className="flex flex-wrap items-baseline gap-1.5 min-h-[28px]">
            {selectedFeatures.map((skill) => (
              <span
                key={skill.id}
                className="inline-flex items-center gap-1 rounded-md bg-blue-50 border border-blue-200/80 px-2 py-0.5 text-xs font-semibold text-[#002777] shrink-0 select-none align-baseline"
              >
                <Sparkles className="h-3 w-3 text-blue-600 shrink-0" />
                <span>/{skill.label || skill.id}</span>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedFeatures((prev) => prev.filter((s) => s.id !== skill.id))
                    textareaRef.current?.focus()
                  }}
                  className="ml-0.5 rounded p-0.5 text-blue-400 hover:bg-blue-100 hover:text-blue-700 transition cursor-pointer"
                  title="Quitar skill"
                  aria-label={`Quitar skill ${skill.label || skill.id}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}

            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => {
                const value = e.target.value
                setDraft(value)
                const cursor = e.target.selectionStart ?? value.length
                const textBeforeCursor = value.slice(0, cursor)
                const slashMatch = textBeforeCursor.match(/(?:^|\s)\/([a-zA-Z0-9_-]*)$/)
                setRubricMenuOpen(Boolean(slashMatch))
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  onSubmitForm(e)
                }
              }}
              onFocus={() => {
                const cursor = textareaRef.current?.selectionStart ?? draft.length
                const textBeforeCursor = draft.slice(0, cursor)
                const slashMatch = textBeforeCursor.match(/(?:^|\s)\/([a-zA-Z0-9_-]*)$/)
                setRubricMenuOpen(Boolean(slashMatch))
              }}
              placeholder={
                selectedFeatures.length > 0
                  ? 'Describe qué debe generar el agente...'
                  : placeholder
              }
              disabled={isGenerating}
              style={{ height: `${textareaHeight}px` }}
              className="flex-1 min-w-[120px] bg-transparent px-1 pr-16 text-xs text-slate-800 outline-none resize-none placeholder:text-slate-400 disabled:opacity-60 font-sans overflow-y-auto scrollbar-thin transition-[height] duration-150 ease-out leading-normal m-0 p-0 align-baseline"
            />
          </div>

          {/* Slash Rubric Menu */}
          {rubricMenuOpen && (
            <div
              tabIndex={-1}
              className="absolute left-3 right-3 bottom-14 z-40 max-h-72 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-xl"
            >
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  setRubricMenuOpen(false)
                }}
                className="absolute top-2.5 right-2.5 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-800 transition shadow-xs cursor-pointer"
                title="Cerrar prompts disponibles"
                aria-label="Cerrar prompts disponibles"
              >
                <X className="h-4 w-4" />
              </button>

              <div className="flex items-center px-2 py-2 border-b border-slate-100 mb-1 pr-10">
                <span className="text-xs font-bold text-slate-800">Prompts y Skills disponibles</span>
              </div>
              {visiblePromptFeatures.length === 0 ? (
                <div className="px-2 py-3 text-xs text-slate-500">No hay prompts disponibles para este rol.</div>
              ) : (
                visiblePromptFeatures.map((feature) => {
                  const meta = FEATURE_METAS.find((item) => item.id === feature)
                  return (
                    <button
                      key={feature}
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        const label = (meta?.title || feature).replace(/\s*\(\/[^)]+\)/, '')
                        setSelectedFeatures((prev) => {
                          if (prev.some((s) => s.id === feature)) return prev
                          return [...prev, { id: feature, label }]
                        })
                        setDraft((prev) => {
                          const cursor = textareaRef.current?.selectionStart ?? prev.length
                          const before = prev.slice(0, cursor).replace(/(?:^|\s)\/([a-zA-Z0-9_-]*)$/, '')
                          const after = prev.slice(cursor)
                          return `${before} ${after}`.trimStart()
                        })
                        setRubricMenuOpen(false)
                        setTimeout(() => {
                          textareaRef.current?.focus()
                        }, 0)
                      }}
                      className="w-full rounded-xl px-2.5 py-2 text-left hover:bg-blue-50 transition cursor-pointer"
                    >
                      <span className="block text-xs font-semibold text-slate-800">/{feature}</span>
                      <span className="block text-[10px] text-slate-500 truncate">{meta?.title || `Prompt de ${feature}`}</span>
                    </button>
                  )
                })
              )}
            </div>
          )}

          {/* Bottom Actions Row */}
          <div className="flex items-center justify-between gap-2 pt-1 border-t border-slate-200/60">
            <div className="flex min-w-0 flex-1 items-center gap-1.5">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setPlusMenuOpen((open) => !open)}
                  disabled={uploading}
                  className="h-7 w-7 rounded-full bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 flex items-center justify-center transition shrink-0 cursor-pointer shadow-2xs"
                  title="Adjuntar archivos o generar borrador"
                >
                  {uploading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-4 w-4" />}
                </button>
                {plusMenuOpen && (
                  <div className="absolute left-0 bottom-10 z-50 w-72 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl">
                    <button
                      type="button"
                      onClick={() => {
                        setPlusMenuOpen(false)
                        fileInputRef.current?.click()
                      }}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 transition"
                    >
                      <FileText className="h-4 w-4 text-slate-500" />
                      <span>
                        <span className="block text-xs font-semibold text-slate-800">Agregar fotos y archivos</span>
                        <span className="block text-[10px] text-slate-400">Cargar desde la computadora</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setTemplateMenuOpen((open) => !open)}
                      className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-blue-50 transition"
                    >
                      <span className="flex items-center gap-3">
                        <Sparkles className="h-4 w-4 text-blue-500" />
                        <span>
                          <span className="block text-xs font-semibold text-slate-800">Generar borrador</span>
                          <span className="block text-[10px] text-slate-400">Usar una plantilla corporativa</span>
                        </span>
                      </span>
                      <ChevronDown className={`h-3 w-3 text-slate-400 transition ${templateMenuOpen ? 'rotate-180' : ''}`} />
                    </button>
                    {templateMenuOpen && (
                      <div
                        className="mt-1 max-h-48 overflow-y-auto border-t border-slate-100 pt-1 scrollbar-thin"
                        onScroll={onTemplateListScroll}
                      >
                        <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">Plantilla corporativa</div>
                        {corporateTemplates.length === 0 ? (
                          <div className="px-3 py-2 text-xs text-slate-500">No hay plantillas disponibles.</div>
                        ) : (
                          visibleCorporateTemplates.map((template) => (
                            <button
                              key={template.id}
                              type="button"
                              onClick={() => {
                                setSelectedTemplateId(template.id)
                                setPlusMenuOpen(false)
                                setTemplateMenuOpen(false)
                                focusEditorEnd()
                              }}
                              className={`w-full rounded-lg px-3 py-2 text-left transition ${selectedTemplateId === template.id ? 'bg-blue-50 text-[#002777]' : 'hover:bg-slate-50 text-slate-700'}`}
                            >
                              <span className="block text-xs font-semibold truncate">{template.title}</span>
                              <span className="block text-[10px] text-slate-400 truncate">{template.module || template.filename}</span>
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
              <VoiceInput
                disabled={isGenerating}
                onTranscriptionReady={(transcribedText) => {
                  setDraft((prev) => (prev ? `${prev} ${transcribedText}` : transcribedText))
                  focusEditorEnd()
                }}
              />
            </div>

            {/* Sources & Send */}
            <div className="flex items-center gap-2 relative">
              <button
                type="button"
                onClick={() => toggleSource('knowledge')}
                className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-xl border transition cursor-pointer ${
                  isKnowledgeActive
                    ? 'bg-[#002777] text-white border-[#002777] shadow-2xs'
                    : 'bg-white text-slate-600 border-slate-200 hover:text-slate-800'
                }`}
              >
                <BookOpen className="h-3.5 w-3.5" />
                <span>Biblioteca</span>
              </button>

              <div
                className="relative"
                onMouseEnter={() => setIntegrationsFlyoutOpen(true)}
                onMouseLeave={() => setIntegrationsFlyoutOpen(false)}
              >
                <button
                  type="button"
                  onClick={toggleAllIntegrations}
                  className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-xl border transition cursor-pointer ${
                    isIntegrationsActive
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

              <button
                type={isGenerating ? 'button' : 'submit'}
                onClick={isGenerating ? onCancelRun : undefined}
                className="h-8 w-8 rounded-full flex items-center justify-center transition shrink-0 shadow-xs ml-1 bg-[#002777] text-white hover:bg-[#003399] cursor-pointer"
                title={isGenerating ? 'Cancelar generación' : 'Enviar consulta'}
              >
                {isGenerating ? (
                  <Square className="h-3.5 w-3.5 fill-white text-white" />
                ) : (
                  <ArrowUp className="h-4 w-4 stroke-[2.5]" />
                )}
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  )
}
