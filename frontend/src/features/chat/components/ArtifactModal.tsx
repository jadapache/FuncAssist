import { useState } from 'react'
import {
  X,
  FileText,
  FileSpreadsheet,
  Download,
  Trash2,
  Undo2,
  Redo2,
  Circle,
  CheckCircle2,
} from 'lucide-react'
import type { Artifact } from '../../../types/artifacts'
import type { UniverAdapter } from '../../document/agent/adapters/UniverAdapter'
import { UniverContainer } from '../../document/univer/UniverContainer'
import { API_BASE, getAuthHeaders } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

interface ArtifactModalProps {
  artifact: Artifact | null
  adapter: UniverAdapter
  canUndo?: boolean
  canRedo?: boolean
  isDirty?: boolean
  isSaving?: boolean
  onUndo?: () => void
  onRedo?: () => void
  onClose: () => void
  onDelete?: (id: string) => void
  onUpdateContent?: (id: string, newContent: string) => void
}

export const ArtifactModal = ({
  artifact,
  adapter,
  canUndo = false,
  canRedo = false,
  isDirty = false,
  isSaving = false,
  onUndo,
  onRedo,
  onClose,
  onDelete,
  onUpdateContent,
}: ArtifactModalProps) => {
  const { toast } = useToast()
  const [downloading, setDownloading] = useState(false)

  if (!artifact) return null

  const handleDownload = async () => {
    const { title, content, extension } = artifact
    setDownloading(true)
    try {
      if (extension === 'txt') {
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title.replace(/\s+/g, '_')}.txt`
        a.click()
        URL.revokeObjectURL(url)
        toast.success('Documento descargado como .txt')
        return
      }

      const endpoint =
        extension === 'xlsx'
          ? `${API_BASE}/api/doc-agent/export-xlsx`
          : `${API_BASE}/api/doc-agent/export-docx`

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ title, content }),
      })

      if (!response.ok) throw new Error(`Error al exportar .${extension}`)

      const arrayBuffer = await response.arrayBuffer()
      const mimeType =
        extension === 'xlsx'
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

      const blob = new Blob([arrayBuffer], { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${title.replace(/\s+/g, '_')}.${extension}`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`Documento descargado como .${extension}`)
    } catch {
      toast.error('Error al exportar el documento.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="flex flex-col h-[90vh] w-full max-w-5xl rounded-3xl bg-white shadow-2xl overflow-hidden border border-slate-200">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-3.5 border-b border-slate-200 bg-white shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-[#002777] border border-blue-200">
              {artifact.extension === 'xlsx' ? (
                <FileSpreadsheet className="h-4 w-4" />
              ) : (
                <FileText className="h-4 w-4" />
              )}
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-slate-900 truncate" title={artifact.title}>
                {artifact.title}
              </h3>
              <p className="text-[11px] text-slate-500 uppercase font-semibold">
                .{artifact.extension} • Vista completa
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Status indicator */}
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border border-slate-200 bg-slate-50 text-slate-600">
              {isDirty ? (
                <>
                  <Circle className="h-2 w-2 fill-amber-500 text-amber-500" />
                  <span>Sin guardar</span>
                </>
              ) : isSaving ? (
                <span>Guardando...</span>
              ) : (
                <>
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span>Guardado</span>
                </>
              )}
            </div>

            {/* Undo / Redo */}
            {onUndo && onRedo && (
              <div className="flex items-center gap-0.5 bg-slate-100 rounded-xl p-0.5 border border-slate-200">
                <button
                  type="button"
                  onClick={onUndo}
                  disabled={!canUndo}
                  className="p-1.5 rounded-lg text-slate-600 hover:bg-white disabled:opacity-30 transition cursor-pointer"
                  title="Deshacer"
                >
                  <Undo2 className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={onRedo}
                  disabled={!canRedo}
                  className="p-1.5 rounded-lg text-slate-600 hover:bg-white disabled:opacity-30 transition cursor-pointer"
                  title="Rehacer"
                >
                  <Redo2 className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            {/* Download */}
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer shadow-2xs"
              title="Descargar documento"
            >
              <Download className="h-3.5 w-3.5" />
              <span>{downloading ? 'Descargando...' : 'Descargar'}</span>
            </button>

            {/* Delete */}
            {onDelete && (
              <button
                type="button"
                onClick={() => {
                  onDelete(artifact.id)
                  onClose()
                }}
                className="p-1.5 rounded-xl text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                title="Eliminar artefacto"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}

            {/* Close */}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-xl text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
              title="Cerrar modal"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Modal Viewport (Univer Document Viewer) */}
        <div className="flex-1 overflow-hidden bg-slate-50 relative">
          <UniverContainer
            adapter={adapter}
            kind={artifact.extension === 'xlsx' ? 'spreadsheet' : 'document'}
            title={artifact.title}
            content={artifact.content}
            images={[]}
            onInspect={() => {}}
            onExport={() => handleDownload()}
            onReloadFixture={() => {}}
            hideHeader={true}
            mode="artifact"
            onContentChange={(newContent: string) => {
              onUpdateContent?.(artifact.id, newContent)
            }}
          />
        </div>
      </div>
    </div>
  )
}

export default ArtifactModal
