/**
 * TemplateBuilderModal.tsx
 * Modular fullscreen WPForms-style builder modal for template editing.
 * Combines header actions, tag sidebar, and Univer visual document viewport.
 */

import React, { useRef } from 'react'
import {
  ArrowLeft,
  Check,
  RefreshCw,
  Save,
  Wand2,
} from 'lucide-react'
import type { CorporateTemplate, TemplateDetail } from '../../../../api/client'
import type { UniverAdapter } from '../../../../features/document/agent/adapters/UniverAdapter'
import { UniverContainer } from '../../../../features/document/univer/UniverContainer'
import { TemplateTagSidebar, type TabSidebar } from './TemplateTagSidebar'
import type { ValidationSummary } from '../../../../features/document/univer/templateValidator'

interface TemplateBuilderModalProps {
  previewTemplate: CorporateTemplate
  previewDetail: TemplateDetail | null
  loadingDetail: boolean
  onClose: () => void
  editedContent: string
  onEditedContentChange: (val: string) => void
  viewMode: 'preview' | 'editor'
  onViewModeChange: (mode: 'preview' | 'editor') => void
  savingContent: boolean
  onSaveBuilder: () => void
  univerAdapter: UniverAdapter
  activeLineIdx: number | null
  onActiveLineIdxChange: (idx: number) => void
  templateValidation: ValidationSummary
  onAutoFix: () => void
  customTags: string[]
  filterQuery: string
  onFilterQueryChange: (q: string) => void
  onInsertTagAtCursor: (tag: string) => void
  showAddCustomTag: boolean
  onToggleAddCustomTag: () => void
  newCustomTagInput: string
  onNewCustomTagInputChange: (val: string) => void
  onAddCustomTag: (e: React.FormEvent) => void
  onDeleteCustomTag: (tag: string) => void
  sidebarTab: TabSidebar
  onSidebarTabChange: (tab: TabSidebar) => void
  collapseFunction: boolean
  onToggleCollapseFunction: () => void
  collapseCustom: boolean
  onToggleCollapseCustom: () => void
  allAvailableTags: string[]
  formatFileSize: (bytes: number) => string
}

export const TemplateBuilderModal: React.FC<TemplateBuilderModalProps> = ({
  previewTemplate,
  previewDetail,
  loadingDetail,
  onClose,
  editedContent,
  onEditedContentChange,
  viewMode,
  onViewModeChange,
  savingContent,
  onSaveBuilder,
  univerAdapter,
  activeLineIdx,
  onActiveLineIdxChange,
  templateValidation,
  onAutoFix,
  customTags,
  filterQuery,
  onFilterQueryChange,
  onInsertTagAtCursor,
  showAddCustomTag,
  onToggleAddCustomTag,
  newCustomTagInput,
  onNewCustomTagInputChange,
  onAddCustomTag,
  onDeleteCustomTag,
  sidebarTab,
  onSidebarTabChange,
  collapseFunction,
  onToggleCollapseFunction,
  collapseCustom,
  onToggleCollapseCustom,
  allAvailableTags,
  formatFileSize,
}) => {
  const editorRef = useRef<HTMLTextAreaElement>(null)

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/80 backdrop-blur-sm flex flex-col overflow-hidden animate-fadeIn font-sans">
      {/* 1. TOP BUILDER BAR */}
      <header className="bg-[#002777] text-white px-5 py-2.5 flex items-center justify-between border-b border-blue-900 shrink-0 shadow-md">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-blue-200 hover:text-white hover:bg-white/10 transition cursor-pointer flex items-center gap-1 text-xs font-semibold"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Volver</span>
          </button>

          <div className="h-4 w-[1px] bg-blue-700" />

          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-white tracking-wide">{previewTemplate.title}</h3>
              <span className="uppercase text-[9px] font-extrabold px-2 py-0.5 rounded-full bg-blue-600/80 text-white">
                .{previewTemplate.file_type}
              </span>
            </div>
            <p className="text-[10px] text-blue-200">
              Archivo: <span className="font-mono text-white">{previewTemplate.filename}</span> • Módulo: <span className="capitalize text-white font-semibold">{previewTemplate.module}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Validation Status Pill */}
          {templateValidation.isValid ? (
            <span className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
              <Check className="h-3.5 w-3.5" />
              <span>{templateValidation.totalPlaceholders} tags válidos</span>
            </span>
          ) : (
            <button
              type="button"
              onClick={onAutoFix}
              className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 cursor-pointer transition"
              title="Clic para auto-corregir sintaxis"
            >
              <Wand2 className="h-3.5 w-3.5" />
              <span>{templateValidation.issues.length} obs. • Auto-reparar</span>
            </button>
          )}

          {/* View Switcher */}
          <div className="flex rounded-lg bg-blue-950/80 p-0.5 border border-blue-700/60 text-[11px]">
            <button
              type="button"
              onClick={() => onViewModeChange('preview')}
              className={`px-2.5 py-1 rounded-md font-semibold transition cursor-pointer ${
                viewMode === 'preview' ? 'bg-white text-[#002777] shadow-xs font-bold' : 'text-blue-200 hover:text-white'
              }`}
            >
              Vista Documento (Edición Directa)
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange('editor')}
              className={`px-2.5 py-1 rounded-md font-semibold transition cursor-pointer ${
                viewMode === 'editor' ? 'bg-white text-[#002777] shadow-xs font-bold' : 'text-blue-200 hover:text-white'
              }`}
            >
              Texto Markdown
            </button>
          </div>

          <button
            type="button"
            onClick={onSaveBuilder}
            disabled={savingContent}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-sm transition cursor-pointer disabled:opacity-50"
          >
            {savingContent ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            <span>Guardar Plantilla</span>
          </button>
        </div>
      </header>

      {/* 2. MAIN BUILDER BODY */}
      <div className="flex-1 flex overflow-hidden bg-slate-100">
        {/* Left Tag Sidebar */}
        <TemplateTagSidebar
          sidebarTab={sidebarTab}
          onSidebarTabChange={onSidebarTabChange}
          previewTemplate={previewTemplate}
          previewDetail={previewDetail}
          customTags={customTags}
          filterQuery={filterQuery}
          onFilterQueryChange={onFilterQueryChange}
          onInsertTag={onInsertTagAtCursor}
          showAddCustomTag={showAddCustomTag}
          onToggleAddCustomTag={onToggleAddCustomTag}
          newCustomTagInput={newCustomTagInput}
          onNewCustomTagInputChange={onNewCustomTagInputChange}
          onAddCustomTag={onAddCustomTag}
          onDeleteCustomTag={onDeleteCustomTag}
          collapseFunction={collapseFunction}
          onToggleCollapseFunction={onToggleCollapseFunction}
          collapseCustom={collapseCustom}
          onToggleCollapseCustom={onToggleCollapseCustom}
          formatFileSize={formatFileSize}
        />

        {/* Right Document Viewport (Canvas + WYSIWYG Floating Toolbar) */}
        <main className="flex-1 overflow-y-auto bg-slate-200/70 flex flex-col items-center">
          {loadingDetail ? (
            <div className="p-16 text-center text-slate-500 flex flex-col items-center justify-center gap-3 my-auto">
              <RefreshCw className="h-8 w-8 animate-spin text-[#002777]" />
              <span className="text-sm font-semibold">Cargando plantilla corporativa...</span>
            </div>
          ) : (
            <div className="w-full flex-1 flex flex-col min-h-0">
              {viewMode === 'editor' ? (
                <div className="p-6 md:p-10 flex-1 flex flex-col max-w-4xl mx-auto w-full space-y-2">
                  <div className="flex items-center justify-between text-xs text-slate-500 pb-1">
                    <span>Editor de plantilla (Modo Código Markdown)</span>
                    <span className="font-mono text-[11px]">Haz clic en cualquier placeholder de la izquierda para insertarlo</span>
                  </div>

                  <textarea
                    ref={editorRef}
                    value={editedContent}
                    onChange={(e) => onEditedContentChange(e.target.value)}
                    className="w-full flex-1 min-h-[600px] p-6 font-mono text-xs text-slate-900 bg-white rounded-lg border border-slate-300 focus:ring-2 focus:ring-[#002777] focus:outline-hidden leading-relaxed resize-none font-medium shadow-sm"
                    placeholder="Edita la plantilla e inserta placeholders {{FECHA}}, {{RESPONSABLE}}, etc..."
                  />
                </div>
              ) : (
                /* Contenedor Univer con Barra Flotante WYSIWYG */
                <div className="flex-1 flex flex-col min-h-0 w-full bg-white shadow-xs">
                  <UniverContainer
                    adapter={univerAdapter}
                    kind={previewTemplate.file_type === 'xlsx' ? 'spreadsheet' : 'document'}
                    title={previewTemplate.title}
                    content={editedContent}
                    headerContent={previewDetail?.header_content}
                    footerContent={previewDetail?.footer_content}
                    images={[]}
                    onInspect={() => {}}
                    onExport={() => {}}
                    onReloadFixture={() => {}}
                    onContentChange={onEditedContentChange}
                    activeLineIndex={activeLineIdx}
                    onActiveLineChange={onActiveLineIdxChange}
                    hideHeader={true}
                    availableTags={allAvailableTags}
                    mode="template"
                  />
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
