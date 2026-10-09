/**
 * TemplateTagSidebar.tsx
 * Modular sidebar component for the Template Builder.
 * Manages system tags, custom tag creation/deletion, placeholder filtering, and document properties.
 */

import React from 'react'
import {
  Tag,
  Plus,
  Trash2,
  Zap,
  Search,
  ChevronDown,
  ChevronRight,
  GripVertical,
} from 'lucide-react'
import type { CorporateTemplate, TemplateDetail } from '../../../../api/client'

export type TabSidebar = 'fields' | 'details'

interface TemplateTagSidebarProps {
  sidebarTab: TabSidebar
  onSidebarTabChange: (tab: TabSidebar) => void
  previewTemplate: CorporateTemplate
  previewDetail: TemplateDetail | null
  customTags: string[]
  filterQuery: string
  onFilterQueryChange: (q: string) => void
  onInsertTag: (tag: string) => void
  showAddCustomTag: boolean
  onToggleAddCustomTag: () => void
  newCustomTagInput: string
  onNewCustomTagInputChange: (val: string) => void
  onAddCustomTag: (e: React.FormEvent) => void
  onDeleteCustomTag: (tag: string) => void
  collapseFunction: boolean
  onToggleCollapseFunction: () => void
  collapseCustom: boolean
  onToggleCollapseCustom: () => void
  formatFileSize: (bytes: number) => string
}

export const TemplateTagSidebar: React.FC<TemplateTagSidebarProps> = ({
  sidebarTab,
  onSidebarTabChange,
  previewTemplate,
  previewDetail,
  customTags,
  filterQuery,
  onFilterQueryChange,
  onInsertTag,
  showAddCustomTag,
  onToggleAddCustomTag,
  newCustomTagInput,
  onNewCustomTagInputChange,
  onAddCustomTag,
  onDeleteCustomTag,
  collapseFunction,
  onToggleCollapseFunction,
  collapseCustom,
  onToggleCollapseCustom,
  formatFileSize,
}) => {
  const filteredSystemTags = (previewDetail?.system_tags || []).filter((t) =>
    t.tag.toLowerCase().includes(filterQuery.toLowerCase()) ||
    t.description.toLowerCase().includes(filterQuery.toLowerCase())
  )
  const filteredCustomTags = customTags.filter((t) =>
    t.toLowerCase().includes(filterQuery.toLowerCase())
  )

  return (
    <aside className="w-80 md:w-96 bg-white border-r border-slate-200 flex flex-col shrink-0 shadow-sm z-10 font-sans">
      {/* Sidebar Header Tabs */}
      <div className="flex border-b border-slate-200 bg-slate-50/80 p-1">
        <button
          type="button"
          onClick={() => onSidebarTabChange('fields')}
          className={`flex-1 py-1.5 text-[11px] font-bold text-center rounded-md transition cursor-pointer ${
            sidebarTab === 'fields'
              ? 'bg-white text-[#002777] shadow-xs border border-slate-200/80'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Placeholders & Campos
        </button>
        <button
          type="button"
          onClick={() => onSidebarTabChange('details')}
          className={`flex-1 py-1.5 text-[11px] font-bold text-center rounded-md transition cursor-pointer ${
            sidebarTab === 'details'
              ? 'bg-white text-[#002777] shadow-xs border border-slate-200/80'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Propiedades
        </button>
      </div>

      {/* TAB 1: PLACEHOLDERS & FIELDS */}
      {sidebarTab === 'fields' && (
        <div className="flex-1 flex flex-col min-h-0">
          {/* Search Bar */}
          <div className="p-3 border-b border-slate-100 bg-slate-50/40">
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={filterQuery}
                onChange={(e) => onFilterQueryChange(e.target.value)}
                placeholder="Buscar placeholder..."
                className="w-full bg-white border border-slate-200 rounded-lg pl-8 pr-3 py-1 text-xs text-slate-800 focus:outline-hidden focus:ring-1 focus:ring-[#002777]"
              />
            </div>
          </div>

          <div className="flex-1 p-3 overflow-y-auto space-y-4 text-xs">
            {/* 1. FUNCTIONAL SYSTEM TAGS */}
            <div>
              <button
                type="button"
                onClick={onToggleCollapseFunction}
                className="w-full flex items-center justify-between font-bold text-slate-700 text-xs mb-2 hover:text-[#002777] cursor-pointer"
              >
                <div className="flex items-center gap-1.5">
                  <Tag className="h-3.5 w-3.5 text-[#002777]" />
                  <span>Placeholders del Sistema ({filteredSystemTags.length})</span>
                </div>
                {collapseFunction ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>

              {!collapseFunction && (
                <div className="grid grid-cols-1 gap-1.5">
                  {filteredSystemTags.map((item) => (
                    <div
                      key={item.tag}
                      onClick={() => onInsertTag(item.tag)}
                      draggable={true}
                      onDragStart={(e) => e.dataTransfer.setData('text/plain', item.tag)}
                      className="group flex items-center justify-between p-2 bg-slate-50 hover:bg-blue-50/70 border border-slate-200 hover:border-blue-300 rounded-lg transition cursor-grab active:cursor-grabbing shadow-2xs"
                      title="Haz clic para insertar o arrastra al documento"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <GripVertical className="h-3.5 w-3.5 text-slate-300 group-hover:text-blue-400 shrink-0" />
                        <div className="min-w-0">
                          <span className="font-mono text-[11px] font-bold text-[#002777] block truncate">
                            {`{{${item.tag}}}`}
                          </span>
                          <span className="text-[10px] text-slate-500 block truncate">{item.description}</span>
                        </div>
                      </div>
                      <span className="text-[9px] font-semibold text-blue-600 bg-blue-100/60 px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition shrink-0">
                        + Insertar
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 2. CUSTOM TEMPLATE TAGS */}
            <div className="pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between mb-2">
                <button
                  type="button"
                  onClick={onToggleCollapseCustom}
                  className="flex items-center gap-1.5 font-bold text-slate-700 text-xs hover:text-[#002777] cursor-pointer"
                >
                  <Tag className="h-3.5 w-3.5 text-indigo-600" />
                  <span>Personalizados ({filteredCustomTags.length})</span>
                </button>

                <button
                  type="button"
                  onClick={onToggleAddCustomTag}
                  className="px-2 py-0.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded text-[10px] font-bold flex items-center gap-1 transition cursor-pointer border border-indigo-200"
                >
                  <Plus className="h-3 w-3" />
                  <span>Nuevo</span>
                </button>
              </div>

              {showAddCustomTag && (
                <form onSubmit={onAddCustomTag} className="mb-3 p-2 bg-indigo-50/50 border border-indigo-200 rounded-lg space-y-2">
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={newCustomTagInput}
                      onChange={(e) => onNewCustomTagInputChange(e.target.value)}
                      placeholder="Ej: APODERADO_LEGAL"
                      className="w-full bg-white border border-slate-300 rounded px-2 py-1 text-xs font-mono uppercase focus:ring-1 focus:ring-indigo-500"
                      autoFocus
                    />
                    <button
                      type="submit"
                      className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded transition shrink-0 cursor-pointer"
                    >
                      Agregar
                    </button>
                  </div>
                </form>
              )}

              {!collapseCustom && (
                <div className="grid grid-cols-1 gap-1.5">
                  {filteredCustomTags.length === 0 ? (
                    <p className="text-[11px] text-slate-400 italic p-2 bg-slate-50 rounded-lg text-center">
                      No hay placeholders personalizados creados.
                    </p>
                  ) : (
                    filteredCustomTags.map((tag) => (
                      <div
                        key={tag}
                        onClick={() => onInsertTag(tag)}
                        draggable={true}
                        onDragStart={(e) => e.dataTransfer.setData('text/plain', tag)}
                        className="group flex items-center justify-between p-2 bg-indigo-50/40 hover:bg-indigo-50 border border-indigo-200/80 rounded-lg transition cursor-grab active:cursor-grabbing shadow-2xs"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <GripVertical className="h-3.5 w-3.5 text-indigo-300 shrink-0" />
                          <span className="font-mono text-[11px] font-bold text-indigo-900 truncate">
                            {`{{${tag}}}`}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-[9px] font-semibold text-indigo-600 bg-indigo-100 px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition">
                            + Insertar
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              onDeleteCustomTag(tag)
                            }}
                            className="p-1 hover:text-red-600 text-slate-400 rounded transition cursor-pointer"
                            title="Eliminar placeholder"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: DOCUMENT DETAILS */}
      {sidebarTab === 'details' && (
        <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs text-slate-700">
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
            <h4 className="font-bold text-slate-900 text-xs">Propiedades del Documento</h4>
            <p className="text-[11px] text-slate-500">Informaciones de la plantilla de origen.</p>

            <div className="space-y-1.5 pt-2 border-t border-slate-200">
              <div className="flex justify-between">
                <span className="text-slate-500">Título:</span>
                <span className="font-bold text-slate-800">{previewTemplate.title}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Módulo:</span>
                <span className="font-bold text-[#002777] capitalize">{previewTemplate.module}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Formato:</span>
                <span className="font-mono text-slate-900">.{previewTemplate.file_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Tamaño:</span>
                <span>{formatFileSize(previewTemplate.file_size)}</span>
              </div>
            </div>
          </div>

          <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl text-[#002777] space-y-1 text-xs">
            <h5 className="font-bold text-[#002777] flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5 text-[#002777]" />
              <span>Etiquetas Automáticas:</span>
            </h5>
            <p className="text-[11px] leading-relaxed text-slate-700">
              Etiquetas como <code className="font-mono bg-blue-100 px-1 rounded text-[#002777]">{'{{PAGINA}}'}</code> o <code className="font-mono bg-blue-100 px-1 rounded text-[#002777]">{'{{FECHA_HOY}}'}</code> son calculadas automáticamente sin llamadas adicionales a la IA.
            </p>
          </div>
        </div>
      )}
    </aside>
  )
}
