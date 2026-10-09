import { X, Layers, Tag, Table as TableIcon, Image as ImageIcon, CheckCircle, Code } from 'lucide-react'
import type { CanonicalDocumentState } from '../../../features/document/agent/core/types'

interface DocumentInspectorModalProps {
  state: CanonicalDocumentState | null
  isOpen: boolean
  onClose: () => void
}

export const DocumentInspectorModal = ({ state, isOpen, onClose }: DocumentInspectorModalProps) => {
  if (!isOpen || !state) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-indigo-50 text-indigo-700 rounded-xl">
              <Layers className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base">Inspector Canónico de Documento (DocumentAgent)</h3>
              <p className="text-xs text-slate-500">
                Representación intermedia desacoplada del motor ({state.kind.toUpperCase()})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6 text-sm">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Tipo</span>
              <span className="font-bold text-slate-900 capitalize">{state.kind}</span>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Secciones</span>
              <span className="font-bold text-indigo-600">{state.sections.length}</span>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Imágenes</span>
              <span className="font-bold text-emerald-600">{state.totalImages}</span>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Tablas</span>
              <span className="font-bold text-amber-600">{state.tablesSummary.length}</span>
            </div>
          </div>

          {/* Sections List */}
          <div>
            <h4 className="font-bold text-slate-900 mb-2 flex items-center gap-1.5">
              <CheckCircle className="h-4 w-4 text-indigo-600" />
              Secciones Identificadas ({state.sections.length})
            </h4>
            <div className="space-y-2">
              {state.sections.map((sec) => (
                <div key={sec.id} className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-start justify-between">
                  <div>
                    <span className="font-semibold text-slate-800 text-xs flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded-sm bg-indigo-100 text-indigo-700 text-[10px] font-mono">
                        H{sec.level}
                      </span>
                      {sec.title}
                    </span>
                    <p className="text-xs text-slate-500 mt-1 line-clamp-1 italic">
                      "{sec.previewText || 'Sin texto inicial'}"
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {sec.images.length > 0 && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-800">
                        <ImageIcon className="h-3 w-3" /> {sec.images.length}
                      </span>
                    )}
                    {sec.tables.length > 0 && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">
                        <TableIcon className="h-3 w-3" /> {sec.tables.length}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Tags */}
          <div>
            <h4 className="font-bold text-slate-900 mb-2 flex items-center gap-1.5">
              <Tag className="h-4 w-4 text-blue-600" />
              Placeholder Tags Detectados ({state.tagsPresent.length})
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {state.tagsPresent.map((tag) => (
                <span
                  key={tag}
                  className="px-2.5 py-1 bg-blue-50 border border-blue-200 text-blue-800 rounded-lg text-xs font-mono font-medium"
                >
                  {`{{${tag}}}`}
                </span>
              ))}
            </div>
          </div>

          {/* Raw JSON */}
          <details className="group">
            <summary className="cursor-pointer font-semibold text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 select-none">
              <Code className="h-3.5 w-3.5" />
              Ver Payload JSON Canónico Completo
            </summary>
            <pre className="mt-2 p-3 bg-slate-900 text-slate-100 rounded-xl text-[11px] font-mono overflow-x-auto max-h-48">
              {JSON.stringify(state, null, 2)}
            </pre>
          </details>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-xl text-xs font-semibold shadow-xs transition-colors"
          >
            Cerrar Inspector
          </button>
        </div>
      </div>
    </div>
  )
}
