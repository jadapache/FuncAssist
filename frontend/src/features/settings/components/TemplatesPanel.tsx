/**
 * TemplatesPanel.tsx
 * Main orchestrator for Corporate Templates Management and AI Rules & Rubrics.
 * Decoupled into modular components: TemplatesListSection, TemplateBuilderModal, and TemplateTagSidebar.
 */

import type { FormEvent } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileText, Sparkles } from 'lucide-react'
import { api, type CorporateTemplate, type TemplateDetail } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'
import { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'
import {
  validateTemplateContent,
  autoFixTemplateIssues,
  type ValidationSummary,
} from '../../../features/document/univer/templateValidator'
import { AiPromptsRubricsEditor } from './AiPromptsRubricsEditor'
import { TemplatesListSection } from './templates/TemplatesListSection'
import { TemplateBuilderModal } from './templates/TemplateBuilderModal'
import type { TabSidebar } from './templates/TemplateTagSidebar'

export const TemplatesPanel = () => {
  const { toast } = useToast()

  const [panelSection, setPanelSection] = useState<'corporate' | 'ai_rules'>('corporate')
  const [templates, setTemplates] = useState<CorporateTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)

  // New template form state
  const [newFile, setNewFile] = useState<File | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newModule, setNewModule] = useState('funcional')
  const [showUploadModal, setShowUploadModal] = useState(false)

  // Edit metadata modal state
  const [editingTemplate, setEditingTemplate] = useState<CorporateTemplate | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editModule, setEditModule] = useState('')

  // Builder State
  const [previewTemplate, setPreviewTemplate] = useState<CorporateTemplate | null>(null)
  const [previewDetail, setPreviewDetail] = useState<TemplateDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [editedContent, setEditedContent] = useState<string>('')
  const [customTags, setCustomTags] = useState<string[]>([])
  const [newCustomTagInput, setNewCustomTagInput] = useState<string>('')
  const [showAddCustomTag, setShowAddCustomTag] = useState<boolean>(false)
  const [sidebarTab, setSidebarTab] = useState<TabSidebar>('fields')
  const [viewMode, setViewMode] = useState<'preview' | 'editor'>('preview')
  const [savingContent, setSavingContent] = useState<boolean>(false)
  const [filterQuery, setFilterQuery] = useState<string>('')
  const [activeLineIdx, setActiveLineIdx] = useState<number | null>(0)
  const [collapseFunction, setCollapseFunction] = useState<boolean>(false)
  const [collapseCustom, setCollapseCustom] = useState<boolean>(false)

  const univerAdapter = useMemo(() => new UniverAdapter('document'), [])

  useEffect(() => {
    if (previewTemplate && editedContent !== undefined) {
      void univerAdapter.loadTemplate(
        editedContent,
        previewTemplate.file_type === 'xlsx' ? 'spreadsheet' : 'document',
        previewTemplate.title
      )
    }
  }, [editedContent, previewTemplate, univerAdapter])

  const loadTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.getTemplates()
      setTemplates(res.templates || [])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al cargar las plantillas')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void loadTemplates()
  }, [loadTemplates])

  // Load template detail when selected
  useEffect(() => {
    if (!previewTemplate) {
      setPreviewDetail(null)
      setEditedContent('')
      setCustomTags([])
      return
    }

    const fetchDetail = async () => {
      setLoadingDetail(true)
      try {
        const detail = await api.getTemplateContent(previewTemplate.id)
        setPreviewDetail(detail)
        setEditedContent(detail.content || '')

        const defaultTags = (detail.system_tags || []).map((t) => t.tag)
        const extra = (detail.template.tags || []).filter((t) => !defaultTags.includes(t))
        setCustomTags(extra)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error al cargar contenido de la plantilla')
      } finally {
        setLoadingDetail(false)
      }
    }

    void fetchDetail()
  }, [previewTemplate, toast])

  const formatFileSize = (bytes: number) => {
    if (!bytes) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  const handleFilePicked = (picked: FileList | null) => {
    if (!picked?.length) return
    const file = picked[0]
    setNewFile(file)
    if (!newTitle) {
      setNewTitle(file.name.replace(/\.[^/.]+$/, ''))
    }
  }

  const handleUploadSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!newFile) {
      toast.error('Por favor selecciona un archivo (.doc, .docx, .xlsx)')
      return
    }
    setUploading(true)
    try {
      const res = await api.uploadTemplate(newFile, newTitle, newModule)
      setTemplates((prev) => [...prev, res.template])
      toast.success(`Plantilla "${res.template.title}" cargada exitosamente`)
      setNewFile(null)
      setNewTitle('')
      setShowUploadModal(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al subir la plantilla')
    } finally {
      setUploading(false)
    }
  }

  const handleStartEdit = (template: CorporateTemplate) => {
    setEditingTemplate(template)
    setEditTitle(template.title)
    setEditModule(template.module)
  }

  const handleSaveEdit = async () => {
    if (!editingTemplate) return
    try {
      const res = await api.updateTemplate(editingTemplate.id, {
        title: editTitle,
        module: editModule,
      })
      setTemplates((prev) =>
        prev.map((t) => (t.id === editingTemplate.id ? res.template : t)),
      )
      toast.success('Metadatos de la plantilla actualizados correctamente')
      setEditingTemplate(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al actualizar plantilla')
    }
  }

  const handleSaveBuilder = async () => {
    if (!previewTemplate) return
    setSavingContent(true)
    try {
      const systemTags = (previewDetail?.system_tags || []).map((t) => t.tag)
      const allTags = Array.from(new Set([...systemTags, ...customTags]))

      const res = await api.updateTemplate(previewTemplate.id, {
        content: editedContent,
        tags: allTags,
      })
      setTemplates((prev) =>
        prev.map((t) => (t.id === previewTemplate.id ? res.template : t)),
      )
      toast.success('¡Plantilla y placeholders guardados exitosamente!')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar la plantilla')
    } finally {
      setSavingContent(false)
    }
  }

  const handleDelete = async (template: CorporateTemplate) => {
    if (!window.confirm(`¿Estás seguro de eliminar la plantilla "${template.title}"?`)) return
    try {
      await api.deleteTemplate(template.id)
      setTemplates((prev) => prev.filter((t) => t.id !== template.id))
      toast.success('Plantilla eliminada correctamente')
      if (previewTemplate?.id === template.id) {
        setPreviewTemplate(null)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al eliminar plantilla')
    }
  }

  const allAvailableTags = useMemo(() => {
    const systemTags = (previewDetail?.system_tags || []).map((t) => t.tag)
    return Array.from(new Set([...systemTags, ...customTags]))
  }, [previewDetail, customTags])

  const templateValidation = useMemo<ValidationSummary>(() => {
    return validateTemplateContent(editedContent, allAvailableTags)
  }, [editedContent, allAvailableTags])

  const handleAutoFix = () => {
    const fixed = autoFixTemplateIssues(editedContent)
    setEditedContent(fixed)
    toast.success('¡Sintaxis de placeholders y estructura auto-corregida!')
  }

  const insertTagAtCursor = (tagName: string) => {
    const formattedTag = `{{${tagName.replace(/[{}]/g, '').toUpperCase()}}}`
    const lines = (editedContent || '').split(/\r?\n/)
    const targetIdx =
      activeLineIdx !== null && activeLineIdx >= 0 && activeLineIdx < lines.length
        ? activeLineIdx
        : Math.max(0, lines.length - 1)

    const targetLine = lines[targetIdx] || ''
    if (targetLine.trim().startsWith('|') && targetLine.trim().endsWith('|')) {
      const lastPipeIdx = targetLine.lastIndexOf('|')
      const beforePipe = targetLine.substring(0, lastPipeIdx).trimEnd()
      lines[targetIdx] = `${beforePipe} ${formattedTag} |`
    } else {
      lines[targetIdx] = targetLine.trim() ? `${targetLine} ${formattedTag}` : formattedTag
    }
    setEditedContent(lines.join('\n'))
    toast.success(`Placeholder ${formattedTag} insertado en la plantilla`)
  }

  const handleAddCustomTag = (e: FormEvent) => {
    e.preventDefault()
    const clean = newCustomTagInput.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '')
    if (!clean) {
      toast.error('Nombre de etiqueta no válido')
      return
    }
    if (customTags.includes(clean)) {
      toast.error('Esta etiqueta ya existe')
      return
    }
    setCustomTags((prev) => [...prev, clean])
    setNewCustomTagInput('')
    setShowAddCustomTag(false)
    toast.success(`Etiqueta personalizada {{${clean}}} agregada`)
  }

  const handleDeleteCustomTag = (tagName: string) => {
    setCustomTags((prev) => prev.filter((t) => t !== tagName))
    toast.success(`Etiqueta {{${tagName}}} removida`)
  }

  return (
    <div className="space-[#f8fafc] min-h-screen space-y-6 font-sans">
      {/* Top Section Tabs Nav */}
      <div className="flex border-b border-slate-200 bg-white px-6 pt-4 gap-6 text-sm font-semibold">
        <button
          type="button"
          onClick={() => setPanelSection('corporate')}
          className={`pb-3 flex items-center gap-2 border-b-2 transition cursor-pointer ${
            panelSection === 'corporate'
              ? 'border-[#002777] text-[#002777] font-bold'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText className="h-4 w-4" />
          <span>Plantillas Corporativas & Documentos</span>
        </button>

        <button
          type="button"
          onClick={() => setPanelSection('ai_rules')}
          className={`pb-3 flex items-center gap-2 border-b-2 transition cursor-pointer ${
            panelSection === 'ai_rules'
              ? 'border-[#002777] text-[#002777] font-bold'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Sparkles className="h-4 w-4 text-purple-600" />
          <span>Prompting IA & Reglas por Rol</span>
        </button>
      </div>

      {/* Main Section Content */}
      <div className="px-6 pb-12">
        {panelSection === 'corporate' ? (
          <TemplatesListSection
            templates={templates}
            loading={loading}
            onSelectTemplate={(t) => setPreviewTemplate(t)}
            onStartEdit={handleStartEdit}
            onDelete={handleDelete}
            showUploadModal={showUploadModal}
            onSetShowUploadModal={setShowUploadModal}
            newFile={newFile}
            newTitle={newTitle}
            onSetNewTitle={setNewTitle}
            newModule={newModule}
            onSetNewModule={setNewModule}
            uploading={uploading}
            onFilePicked={handleFilePicked}
            onUploadSubmit={handleUploadSubmit}
            editingTemplate={editingTemplate}
            onSetEditingTemplate={setEditingTemplate}
            editTitle={editTitle}
            onSetEditTitle={setEditTitle}
            editModule={editModule}
            onSetEditModule={setEditModule}
            onSaveEdit={handleSaveEdit}
            formatFileSize={formatFileSize}
          />
        ) : (
          <AiPromptsRubricsEditor />
        )}

        {/* Builder Modal */}
        {previewTemplate && (
          <TemplateBuilderModal
            previewTemplate={previewTemplate}
            previewDetail={previewDetail}
            loadingDetail={loadingDetail}
            onClose={() => setPreviewTemplate(null)}
            editedContent={editedContent}
            onEditedContentChange={setEditedContent}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            savingContent={savingContent}
            onSaveBuilder={handleSaveBuilder}
            univerAdapter={univerAdapter}
            activeLineIdx={activeLineIdx}
            onActiveLineIdxChange={(idx) => setActiveLineIdx(idx)}
            templateValidation={templateValidation}
            onAutoFix={handleAutoFix}
            customTags={customTags}
            filterQuery={filterQuery}
            onFilterQueryChange={setFilterQuery}
            onInsertTagAtCursor={insertTagAtCursor}
            showAddCustomTag={showAddCustomTag}
            onToggleAddCustomTag={() => setShowAddCustomTag(!showAddCustomTag)}
            newCustomTagInput={newCustomTagInput}
            onNewCustomTagInputChange={setNewCustomTagInput}
            onAddCustomTag={handleAddCustomTag}
            onDeleteCustomTag={handleDeleteCustomTag}
            sidebarTab={sidebarTab}
            onSidebarTabChange={setSidebarTab}
            collapseFunction={collapseFunction}
            onToggleCollapseFunction={() => setCollapseFunction(!collapseFunction)}
            collapseCustom={collapseCustom}
            onToggleCollapseCustom={() => setCollapseCustom(!collapseCustom)}
            allAvailableTags={allAvailableTags}
            formatFileSize={formatFileSize}
          />
        )}
      </div>
    </div>
  )
}
