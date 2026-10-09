import { useCallback, useEffect, useState } from 'react'
import {
  FileText,
  FileSpreadsheet,
  FileCode2,
  Plus,
  PanelRightClose,
  PanelRightOpen,
  ChevronLeft,
  Undo2,
  Redo2,
  Download,
  Loader2,
  Circle,
  CheckCircle2,
  MoreVertical,
  Trash2,
  Edit3,
  FileCheck,
  Copy,
  RefreshCw,
} from 'lucide-react'
import type { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'
import { UniverContainer } from '../../../features/document/univer/UniverContainer'
import { useToast } from '../../../context/ToastContext'
import type { Artifact } from '../../../types/artifacts'

export type ArtifactItem = Artifact


interface ArtifactsStudioProps {
  adapter: UniverAdapter
  artifacts: ArtifactItem[]
  activeArtifactId: string | null
  isCollapsed: boolean
  onToggleCollapse: () => void
  onSelectArtifact: (id: string) => void
  onCreateArtifact: (title?: string, extension?: 'docx' | 'xlsx' | 'txt') => void
  onDeleteArtifact: (id: string) => void
  onRenameArtifact: (id: string, newTitle: string) => void
  onUpdateArtifactContent: (id: string, newContent: string) => void

  // Undo/Redo from parent
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void

  // Save state
  isDirty: boolean
  isSaving: boolean

  // Regenerar callback
  onRegenerate?: () => void
}

/**
 * Panel de Artefactos (Claude / Gemini / NotebookLM style).
 * Muestra la navegación por migas de pan (< Artefactos / Documento),
 * barra secundaria de título + guardado/copiar, y canvas visual Univer encuadrado sin desbordamientos.
 */
export const ArtifactsStudio = ({
  adapter,
  artifacts,
  activeArtifactId,
  isCollapsed,
  onToggleCollapse,
  onSelectArtifact,
  onCreateArtifact,
  onDeleteArtifact,
  onRenameArtifact,
  onUpdateArtifactContent,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  isDirty,
  isSaving,
  onRegenerate,
}: ArtifactsStudioProps) => {
  const { toast } = useToast()

  // View mode: 'list' (Artefactos list) or 'editor' (Visual document editor)
  const [viewMode, setViewMode] = useState<'list' | 'editor'>('list')
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const activeArtifact = artifacts.find((a) => a.id === activeArtifactId) || artifacts[0] || null

  // Switch to editor when an artifact is selected or created
  useEffect(() => {
    if (activeArtifactId && artifacts.length > 0) {
      setViewMode('editor')
    }
  }, [activeArtifactId, artifacts.length])

  // Keyboard shortcuts for Undo/Redo in editor
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        if (e.shiftKey) {
          e.preventDefault()
          onRedo()
        } else {
          e.preventDefault()
          onUndo()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onUndo, onRedo])

  // Copy document text to clipboard
  const handleCopyContent = () => {
    if (!activeArtifact) return
    navigator.clipboard.writeText(activeArtifact.content)
    toast.success('Contenido copiado al portapapeles')
  }

  // Export/Download handler considering document extension
  const handleExport = useCallback(
    async (targetFormat?: 'docx' | 'xlsx' | 'txt' | 'json') => {
      if (!activeArtifact) return
      const format = targetFormat || activeArtifact.extension
      const title = activeArtifact.title
      const content = activeArtifact.content

      try {
        if (format === 'txt') {
          const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${title.replace(/\s+/g, '_')}.txt`
          a.click()
          URL.revokeObjectURL(url)
          toast.success(`Documento descargado como .txt`)
          return
        }

        if (format === 'json') {
          const blob = new Blob([content], { type: 'application/json' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${title.replace(/\s+/g, '_')}.json`
          a.click()
          URL.revokeObjectURL(url)
          toast.success(`Documento descargado como .json`)
          return
        }

        const endpoint = format === 'docx' ? '/api/doc-agent/export-docx' : '/api/doc-agent/export-xlsx'
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, content }),
        })

        if (!response.ok) throw new Error(`Error al exportar ${format}`)

        const arrayBuffer = await response.arrayBuffer()
        const mimeType =
          format === 'docx'
            ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        const blob = new Blob([arrayBuffer], { type: mimeType })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title.replace(/\s+/g, '_')}.${format}`
        a.click()
        URL.revokeObjectURL(url)
        toast.success(`Documento descargado como .${format}`)
      } catch (err) {
        console.error(err)
        toast.error('Error al exportar el documento.')
      }
    },
    [activeArtifact, toast],
  )

  const handleStartRename = (art: ArtifactItem) => {
    setRenamingId(art.id)
    setRenameValue(art.title)
    setMenuOpenId(null)
  }

  const handleSaveRename = (id: string) => {
    if (renameValue.trim()) {
      onRenameArtifact(id, renameValue.trim())
    }
    setRenamingId(null)
  }

  // Collapsed Sidebar mode
  if (isCollapsed) {
    return (
      <div className="w-11 bg-white border-l border-slate-200 flex flex-col items-center py-4 gap-4 shrink-0 shadow-xs z-20">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
          title="Abrir Artefactos"
        >
          <PanelRightOpen className="h-5 w-5" />
        </button>
        {isDirty && <Circle className="h-2 w-2 fill-amber-500 text-amber-500" />}
        <div className="mt-auto flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={() => onCreateArtifact()}
            className="p-2 rounded-xl bg-[#002777] text-white hover:bg-[#003399] transition cursor-pointer"
            title="Nuevo Documento"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 min-w-[360px] bg-white border-l border-slate-200 flex flex-col overflow-hidden text-slate-800 shadow-sm">
      {/* View Mode: Artefactos List */}
      {viewMode === 'list' || !activeArtifact ? (
        <div className="flex-1 flex flex-col overflow-hidden bg-white">
          {/* Artefactos Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50/50 shrink-0">
            <div>
              <h2 className="text-base font-bold text-slate-900 tracking-tight">Artefactos</h2>
              <p className="text-xs text-slate-500">
                {artifacts.length} {artifacts.length === 1 ? 'documento en esta sesión' : 'documentos en esta sesión'}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onToggleCollapse}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                title="Colapsar panel"
              >
                <PanelRightClose className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Artefactos Cards List */}
          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            {artifacts.length === 0 ? (
              <div className="text-center py-16 px-4 text-slate-400 space-y-3">
                <FileText className="h-10 w-10 mx-auto opacity-30 text-[#002777]" />
                <p className="text-sm font-medium text-slate-600">No hay artefactos en esta sesión</p>
                <p className="text-xs max-w-xs mx-auto text-slate-500">
                  Pídele al agente que genere un documento de mejoras, especificación o tabla para guardarlo aquí.
                </p>
                <button
                  type="button"
                  onClick={() => onCreateArtifact('Nuevo Documento', 'docx')}
                  className="mt-2 inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-[#002777] hover:bg-[#003399] text-white text-xs font-semibold rounded-xl transition cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Crear nuevo documento
                </button>
              </div>
            ) : (
              artifacts.map((art) => {
                const isActive = art.id === activeArtifact?.id
                const IconComponent =
                  art.extension === 'xlsx'
                    ? FileSpreadsheet
                    : art.extension === 'txt'
                    ? FileCode2
                    : FileText

                return (
                  <div
                    key={art.id}
                    onClick={() => {
                      onSelectArtifact(art.id)
                      setViewMode('editor')
                    }}
                    className={[
                      'group relative flex items-start gap-3.5 p-4 rounded-2xl border transition-all cursor-pointer',
                      isActive
                        ? 'bg-blue-50/60 border-blue-200 shadow-xs ring-1 ring-blue-300/40'
                        : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/80 shadow-xs',
                    ].join(' ')}
                  >
                    <div
                      className={[
                        'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-colors',
                        art.extension === 'xlsx'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-blue-50 text-[#002777] border-blue-200',
                      ].join(' ')}
                    >
                      <IconComponent className="h-5 w-5" />
                    </div>

                    <div className="flex-1 min-w-0 pr-6">
                      {renamingId === art.id ? (
                        <input
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onBlur={() => handleSaveRename(art.id)}
                          onKeyDown={(e) => e.key === 'Enter' && handleSaveRename(art.id)}
                          autoFocus
                          onClick={(e) => e.stopPropagation()}
                          className="bg-white border border-[#002777] text-slate-900 text-sm font-semibold rounded px-2 py-0.5 w-full focus:outline-none"
                        />
                      ) : (
                        <h3 className="text-sm font-bold text-slate-900 group-hover:text-[#002777] transition-colors truncate">
                          {art.title}
                        </h3>
                      )}
                      <p className="text-xs text-slate-500 mt-1 truncate leading-relaxed">
                        {art.subtitle || (art.content ? art.content.slice(0, 75).replace(/[\#\*]/g, '') : 'Sin contenido')}
                      </p>
                      <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-400 font-medium">
                        <span className="uppercase font-bold tracking-wider text-[#002777]">
                          .{art.extension}
                        </span>
                        <span>•</span>
                        <span>{art.updatedAt || 'Hace un momento'}</span>
                      </div>
                    </div>

                    <div className="absolute top-3.5 right-3" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => setMenuOpenId(menuOpenId === art.id ? null : art.id)}
                        className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>

                      {menuOpenId === art.id && (
                        <div className="absolute right-0 top-7 w-40 rounded-xl bg-white border border-slate-200 shadow-xl py-1.5 z-30 text-xs text-slate-700">
                          <button
                            type="button"
                            onClick={() => {
                              onSelectArtifact(art.id)
                              setViewMode('editor')
                              setMenuOpenId(null)
                            }}
                            className="w-full text-left px-3 py-1.5 hover:bg-slate-100 flex items-center gap-2"
                          >
                            <FileCheck className="h-3.5 w-3.5 text-[#002777]" />
                            <span>Abrir Editor</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleStartRename(art)}
                            className="w-full text-left px-3 py-1.5 hover:bg-slate-100 flex items-center gap-2"
                          >
                            <Edit3 className="h-3.5 w-3.5 text-slate-500" />
                            <span>Renombrar</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              handleExport(art.extension)
                              setMenuOpenId(null)
                            }}
                            className="w-full text-left px-3 py-1.5 hover:bg-slate-100 flex items-center gap-2"
                          >
                            <Download className="h-3.5 w-3.5 text-slate-500" />
                            <span>Descargar .{art.extension}</span>
                          </button>

                          <div className="border-t border-slate-100 my-1" />

                          <button
                            type="button"
                            onClick={() => {
                              onDeleteArtifact(art.id)
                              setMenuOpenId(null)
                            }}
                            className="w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600 flex items-center gap-2"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            <span>Eliminar</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      ) : (
        /* View Mode: Visual Document Editor View */
        <div className="flex-1 flex flex-col overflow-hidden bg-white text-slate-900">
          {/* Header Row 1: Breadcrumb Navigation & Global Controls */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-white shrink-0">
            {/* Breadcrumbs: < Artefactos / Documento */}
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className="flex items-center gap-1 hover:text-[#002777] transition cursor-pointer"
                title="Volver a Artefactos"
              >
                <ChevronLeft className="h-4 w-4" />
                <span>Artefactos</span>
              </button>
              <span className="text-slate-300 font-bold">/</span>
              <span className="text-slate-900 font-bold">
                {activeArtifact.extension === 'xlsx' ? 'Hoja de Cálculo' : 'Documento'}
              </span>
              <button
                type="button"
                onClick={() => onDeleteArtifact(activeArtifact.id)}
                className="p-1 text-slate-400 hover:text-red-600 transition ml-1 cursor-pointer"
                title="Eliminar este documento"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Header Right Actions: Undo, Redo, Regenerate, Download, Collapse */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-0.5 bg-slate-50 rounded-xl p-0.5 border border-slate-200">
                <button
                  type="button"
                  onClick={onUndo}
                  disabled={!canUndo}
                  className="p-1.5 rounded-lg text-slate-600 hover:bg-slate-200 disabled:opacity-30 transition cursor-pointer"
                  title="Deshacer (Ctrl+Z)"
                >
                  <Undo2 className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={onRedo}
                  disabled={!canRedo}
                  className="p-1.5 rounded-lg text-slate-600 hover:bg-slate-200 disabled:opacity-30 transition cursor-pointer"
                  title="Rehacer (Ctrl+Shift+Z)"
                >
                  <Redo2 className="h-3.5 w-3.5" />
                </button>
                {onRegenerate && (
                  <button
                    type="button"
                    onClick={onRegenerate}
                    className="p-1.5 rounded-lg text-slate-600 hover:bg-slate-200 transition cursor-pointer"
                    title="Regenerar documento"
                  >
                    <RefreshCw className="h-3.5 w-3.5 text-[#002777]" />
                  </button>
                )}
                {/* Smart Download Icon Button (Downloads in current artifact extension format) */}
                <button
                  type="button"
                  onClick={() => handleExport()}
                  className="p-1.5 rounded-lg text-slate-600 hover:bg-slate-200 transition cursor-pointer"
                  title={`Descargar documento (${activeArtifact.extension.toUpperCase()})`}
                >
                  <Download className="h-3.5 w-3.5 text-[#002777]" />
                </button>
              </div>

              <button
                type="button"
                onClick={onToggleCollapse}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                title="Colapsar panel"
              >
                <PanelRightClose className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Header Row 2: Document Name Sub-bar + Copiar button */}
          <div className="flex items-center justify-between px-5 py-2.5 border-b border-slate-200 bg-slate-50/50 shrink-0">
            {/* Left: Document Name Input */}
            <div className="flex items-center gap-2 min-w-0 flex-1 pr-4">
              <input
                type="text"
                value={activeArtifact.title}
                onChange={(e) => onRenameArtifact(activeArtifact.id, e.target.value)}
                className="bg-transparent text-sm font-bold text-slate-900 focus:outline-none focus:bg-white focus:ring-1 focus:ring-blue-300 rounded px-2 py-1 truncate w-full max-w-md"
                placeholder="Nombre del documento..."
              />
            </div>

            {/* Right: Copiar button */}
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleCopyContent}
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-2xs transition cursor-pointer"
              >
                <Copy className="h-3.5 w-3.5" />
                <span>Copiar</span>
              </button>
            </div>
          </div>

          {/* Main Visual Document Canvas Container (Full edge-to-edge space) */}
          <div className="flex-1 flex flex-col min-h-0 bg-white overflow-hidden">
            <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
              <UniverContainer
                adapter={adapter}
                kind={activeArtifact.extension === 'xlsx' ? 'spreadsheet' : 'document'}
                title={activeArtifact.title}
                content={activeArtifact.content}
                images={[]}
                onInspect={() => {}}
                onExport={(fmt) => handleExport(fmt)}
                onReloadFixture={() => {}}
                onContentChange={(newContent) => {
                  onUpdateArtifactContent(activeArtifact.id, newContent)
                }}
                hideHeader={true}
                mode="artifact"
              />
            </div>

            {/* Bottom Fixed Toolbar: Runtime Info, Save Status Pill & Word Count */}
            <div className="px-5 py-2 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 shrink-0">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase bg-blue-50 text-[#002777] border border-blue-200">
                  Runtime: Univer v1.0.2
                </span>
              </div>

              {/* Center: Save status pill */}
              <div className="flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-white border border-slate-200 text-xs font-semibold shadow-2xs">
                {isSaving ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin text-blue-600" />
                    <span className="text-slate-600 text-[11px]">Guardando...</span>
                  </>
                ) : isDirty ? (
                  <>
                    <Circle className="h-2 w-2 fill-amber-500 text-amber-500" />
                    <span className="text-slate-700 text-[11px]">Cambios no guardados</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                    <span className="text-slate-600 text-[11px]">Guardado</span>
                  </>
                )}
              </div>

              <div className="text-[11px] text-slate-500 font-medium">
                {activeArtifact.content ? `${activeArtifact.content.split(/\s+/).filter(Boolean).length} palabras` : '0 palabras'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
