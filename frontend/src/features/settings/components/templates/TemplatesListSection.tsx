/**
 * TemplatesListSection.tsx
 * Modular component for listing corporate templates, upload modal, and metadata edit modal.
 */

import React, { useRef } from 'react'
import {
  FileText,
  FileSpreadsheet,
  Upload,
  Edit3,
  Trash2,
  Check,
  X,
  RefreshCw,
} from 'lucide-react'
import type { CorporateTemplate } from '../../../../api/client'

interface TemplatesListSectionProps {
  templates: CorporateTemplate[]
  loading: boolean
  onSelectTemplate: (template: CorporateTemplate) => void
  onStartEdit: (template: CorporateTemplate) => void
  onDelete: (template: CorporateTemplate) => void
  showUploadModal: boolean
  onSetShowUploadModal: (show: boolean) => void
  newFile: File | null
  newTitle: string
  onSetNewTitle: (title: string) => void
  newModule: string
  onSetNewModule: (module: string) => void
  uploading: boolean
  onFilePicked: (files: FileList | null) => void
  onUploadSubmit: (e: React.FormEvent) => void
  editingTemplate: CorporateTemplate | null
  onSetEditingTemplate: (t: CorporateTemplate | null) => void
  editTitle: string
  onSetEditTitle: (title: string) => void
  editModule: string
  onSetEditModule: (module: string) => void
  onSaveEdit: () => void
  formatFileSize: (bytes: number) => string
}

export const TemplatesListSection: React.FC<TemplatesListSectionProps> = ({
  templates,
  loading,
  onSelectTemplate,
  onStartEdit,
  onDelete,
  showUploadModal,
  onSetShowUploadModal,
  newFile,
  newTitle,
  onSetNewTitle,
  newModule,
  onSetNewModule,
  uploading,
  onFilePicked,
  onUploadSubmit,
  editingTemplate,
  onSetEditingTemplate,
  editTitle,
  onSetEditTitle,
  editModule,
  onSetEditModule,
  onSaveEdit,
  formatFileSize,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedModuleFilter, setSelectedModuleFilter] = React.useState<string>('todos')

  const filteredTemplates = templates.filter((t) => {
    if (selectedModuleFilter === 'todos') return true
    return t.module === selectedModuleFilter
  })

  return (
    <div className="space-y-6 font-sans">
      {/* Action Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
        <div>
          <h2 className="text-base font-bold text-slate-900">Plantillas Corporativas de QA & Proyectos</h2>
          <p className="text-xs text-slate-500">
            Gestiona los documentos maestros (.docx, .xlsx) utilizados por el Agente IA para redactar reportes.
          </p>
        </div>

        <button
          type="button"
          onClick={() => onSetShowUploadModal(true)}
          className="btn btn-primary text-xs py-2 px-4 flex items-center gap-2 shadow-xs cursor-pointer"
        >
          <Upload className="h-4 w-4" />
          <span>Subir Nueva Plantilla</span>
        </button>
      </div>

      {/* Module Filters */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {['todos', 'funcional', 'qa', 'pm', 'general'].map((mod) => (
          <button
            key={mod}
            type="button"
            onClick={() => setSelectedModuleFilter(mod)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold capitalize transition cursor-pointer ${
              selectedModuleFilter === mod
                ? 'bg-[#002777] text-white shadow-2xs'
                : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
            }`}
          >
            {mod === 'todos' ? 'Todas las Plantillas' : mod}
          </button>
        ))}
      </div>

      {/* Templates Grid */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-2 bg-white rounded-2xl border border-slate-200">
          <RefreshCw className="h-6 w-6 animate-spin text-[#002777]" />
          <span className="text-xs font-semibold">Cargando plantillas...</span>
        </div>
      ) : filteredTemplates.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-2xl border border-dashed border-slate-300 text-slate-500 space-y-2">
          <FileText className="h-10 w-10 text-slate-400 mx-auto" />
          <p className="font-bold text-slate-700 text-sm">No hay plantillas disponibles en esta categoría</p>
          <p className="text-xs text-slate-400">Haz clic en "Subir Nueva Plantilla" para agregar una.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredTemplates.map((template) => (
            <div
              key={template.id}
              className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs hover:shadow-md hover:border-blue-200 transition-all flex flex-col justify-between space-y-4 group"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={`p-2.5 rounded-xl text-white shadow-2xs ${
                        template.file_type === 'xlsx' ? 'bg-emerald-600' : 'bg-[#002777]'
                      }`}
                    >
                      {template.file_type === 'xlsx' ? (
                        <FileSpreadsheet className="h-5 w-5" />
                      ) : (
                        <FileText className="h-5 w-5" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-bold text-slate-900 text-sm group-hover:text-[#002777] transition truncate">
                        {template.title}
                      </h3>
                      <span className="text-[11px] text-slate-500 font-mono">.{template.file_type}</span>
                    </div>
                  </div>

                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-blue-50 text-[#002777] border border-blue-200 shrink-0">
                    {template.module}
                  </span>
                </div>

                <p className="text-xs text-slate-500 truncate" title={template.filename}>
                  Archivo: <span className="font-mono text-slate-700">{template.filename}</span> • <span className="text-slate-400">{formatFileSize(template.file_size)}</span>
                </p>

                {/* Tags preview */}
                <div className="flex flex-wrap gap-1 pt-1">
                  {(template.tags || []).slice(0, 4).map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold bg-slate-100 text-slate-700 border border-slate-200"
                    >
                      {`{{${tag}}}`}
                    </span>
                  ))}
                  {(template.tags || []).length > 4 && (
                    <span className="px-1.5 py-0.5 rounded-md text-[10px] text-slate-400 font-semibold">
                      +{(template.tags || []).length - 4} más
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                <button
                  type="button"
                  onClick={() => onSelectTemplate(template)}
                  className="px-3.5 py-1.5 bg-[#002777] hover:bg-blue-900 text-white font-bold rounded-lg transition shadow-2xs flex items-center gap-1.5 cursor-pointer"
                >
                  <Edit3 className="h-3.5 w-3.5" />
                  <span>Diseñar / Ver</span>
                </button>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onStartEdit(template)}
                    className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                    title="Editar metadatos"
                  >
                    <Edit3 className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => onDelete(template)}
                    className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer"
                    title="Eliminar plantilla"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">Subir Nueva Plantilla Corporativa</h3>
              <button
                type="button"
                onClick={() => onSetShowUploadModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={onUploadSubmit} className="space-y-4">
              <div className="border-2 border-dashed border-slate-300 rounded-xl p-5 text-center bg-slate-50/50 hover:bg-slate-50 transition">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".doc,.docx,.xlsx,.md,.txt"
                  className="hidden"
                  onChange={(e) => onFilePicked(e.target.files)}
                />
                <Upload className="h-8 w-8 text-[#002777] mx-auto mb-2" />
                <p className="text-xs font-semibold text-slate-700">
                  {newFile ? newFile.name : 'Haz clic para elegir plantilla (.doc, .docx, .xlsx)'}
                </p>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="mt-3 btn btn-secondary text-xs py-1 px-3 cursor-pointer"
                >
                  Seleccionar Archivo
                </button>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700 block">Título de la Plantilla</label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => onSetNewTitle(e.target.value)}
                  placeholder="Ej: Formato Corporativo de Mejoras v2"
                  className="input-field text-xs text-slate-800 w-full"
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700 block">Módulo Asociado</label>
                <select
                  value={newModule}
                  onChange={(e) => onSetNewModule(e.target.value)}
                  className="input-field text-xs text-slate-800 w-full"
                >
                  <option value="funcional">Funcional</option>
                  <option value="qa">QA & Pruebas</option>
                  <option value="pm">Project Management</option>
                  <option value="general">General</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => onSetShowUploadModal(false)}
                  className="btn btn-secondary text-xs py-1.5 px-3.5 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={uploading || !newFile}
                  className="btn btn-primary text-xs py-1.5 px-4 flex items-center gap-1.5 cursor-pointer"
                >
                  {uploading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                  <span>Subir Plantilla</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Metadata Modal */}
      {editingTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">Editar Información de la Plantilla</h3>
              <button
                type="button"
                onClick={() => onSetEditingTemplate(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700 block">Título de la Plantilla</label>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => onSetEditTitle(e.target.value)}
                  className="input-field text-xs text-slate-800 w-full"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700 block">Módulo Asociado</label>
                <select
                  value={editModule}
                  onChange={(e) => onSetEditModule(e.target.value)}
                  className="input-field text-xs text-slate-800 w-full"
                >
                  <option value="funcional">Funcional</option>
                  <option value="qa">QA & Pruebas</option>
                  <option value="pm">Project Management</option>
                  <option value="general">General</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => onSetEditingTemplate(null)}
                  className="btn btn-secondary text-xs py-1.5 px-3.5 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={onSaveEdit}
                  className="btn btn-primary text-xs py-1.5 px-4 cursor-pointer"
                >
                  Guardar Cambios
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
