import { useCallback, useEffect, useRef } from 'react'
import {
  Undo2,
  Redo2,
  Download,
  PanelRightClose,
  PanelRightOpen,
  FileText,
  FileSpreadsheet,
  FileCode2,
  CheckCircle2,
  Loader2,
  Circle,
} from 'lucide-react'
import type { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'
import { useToast } from '../../../context/ToastContext'

interface DocumentPanelProps {
  adapter: UniverAdapter
  title: string
  content: string
  isCollapsed: boolean
  onToggleCollapse: () => void
  onContentChange: (newContent: string) => void

  // Undo/Redo from parent
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void

  // Save state
  isDirty: boolean
  isSaving: boolean
  onSave: () => void
}

/**
 * Right panel containing the document canvas with contentEditable,
 * undo/redo toolbar, autosave indicator, and export buttons.
 */
export const DocumentPanel = ({
  title,
  content,
  isCollapsed,
  onToggleCollapse,
  onContentChange,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  isDirty,
  isSaving,
  onSave,
}: DocumentPanelProps) => {
  const { toast } = useToast()
  const editorRef = useRef<HTMLDivElement>(null)

  // Keyboard shortcuts for undo/redo
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

  const handleExport = useCallback(
    async (format: 'docx' | 'xlsx' | 'json') => {
      try {
        if (format === 'json') {
          const blob = new Blob([content], { type: 'application/json' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${title.replace(/\s+/g, '_')}.json`
          a.click()
          URL.revokeObjectURL(url)
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
      } catch (err) {
        console.error(err)
        toast.error('Error al exportar el documento.')
      }
    },
    [content, title, toast],
  )

  // Render lines with markdown-like formatting, hiding {{TAG}} lines
  const renderDocumentContent = () => {
    if (!content.trim()) {
      return (
        <p className="text-sm text-slate-400 italic p-8">
          El documento aparecerá aquí cuando el agente genere contenido...
        </p>
      )
    }

    const lines = content.split('\n')
    return lines.map((line, idx) => {
      const trimmed = line.trim()

      // Hide tag-only lines
      if (/^\{\{[A-Z0-9_]+\}\}$/.test(trimmed)) return null

      // H1
      if (trimmed.startsWith('# ')) {
        return (
          <h1 key={idx} className="text-xl font-bold text-slate-900 mt-5 mb-2 font-serif border-b border-slate-200 pb-2">
            {trimmed.replace('# ', '')}
          </h1>
        )
      }
      // H2
      if (trimmed.startsWith('## ')) {
        return (
          <h2 key={idx} className="text-base font-bold text-[#002777] mt-4 mb-1.5">
            {trimmed.replace('## ', '')}
          </h2>
        )
      }
      // H3
      if (trimmed.startsWith('### ')) {
        return (
          <h3 key={idx} className="text-sm font-bold text-slate-800 mt-3 mb-1">
            {trimmed.replace('### ', '')}
          </h3>
        )
      }
      // List items
      if (trimmed.startsWith('- ')) {
        return (
          <li key={idx} className="text-xs text-slate-700 leading-relaxed ml-4 list-disc">
            {trimmed.replace('- ', '')}
          </li>
        )
      }
      // Table rows
      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        const cells = trimmed.split('|').filter((_, i, arr) => i > 0 && i < arr.length - 1)
        // Skip separator rows
        if (cells.every((c) => /^[\s\-:]*$/.test(c))) return null
        return (
          <div
            key={idx}
            className="grid gap-2 py-1.5 px-2 border-b border-slate-100 text-xs font-mono"
            style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}
          >
            {cells.map((cell, cIdx) => (
              <span key={cIdx} className="truncate text-slate-700">
                {cell.trim()}
              </span>
            ))}
          </div>
        )
      }
      // Empty lines
      if (!trimmed) return <div key={idx} className="h-2" />
      // Normal text
      return (
        <p key={idx} className="text-xs text-slate-700 leading-relaxed">
          {line}
        </p>
      )
    })
  }

  // Collapsed state
  if (isCollapsed) {
    return (
      <div className="w-10 bg-white border-l border-slate-200 flex flex-col items-center py-3 gap-3 shrink-0">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
          title="Mostrar documento"
        >
          <PanelRightOpen className="h-4 w-4" />
        </button>
        {isDirty && <Circle className="h-2 w-2 fill-amber-500 text-amber-500" />}
      </div>
    )
  }

  return (
    <div className="flex-1 min-w-[340px] max-w-[50%] bg-white border-l border-slate-200 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50/80 px-3 py-2 shrink-0">
        <div className="flex items-center gap-2">
          {/* Undo / Redo */}
          <div className="flex items-center gap-0.5 bg-white rounded-lg border border-slate-200 p-0.5">
            <button
              type="button"
              onClick={onUndo}
              disabled={!canUndo}
              className="p-1 rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent transition cursor-pointer"
              title="Deshacer (Ctrl+Z)"
            >
              <Undo2 className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onRedo}
              disabled={!canRedo}
              className="p-1 rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent transition cursor-pointer"
              title="Rehacer (Ctrl+Shift+Z)"
            >
              <Redo2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Save status indicator */}
          <div className="flex items-center gap-1 text-[11px]">
            {isSaving ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                <span className="text-blue-600 font-medium">Guardando...</span>
              </>
            ) : isDirty ? (
              <>
                <Circle className="h-2 w-2 fill-amber-500 text-amber-500" />
                <span className="text-amber-600 font-medium">Sin guardar</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                <span className="text-emerald-600 font-medium">Guardado</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* Export buttons */}
          <button
            type="button"
            onClick={() => handleExport('docx')}
            className="p-1.5 rounded-lg text-slate-500 hover:text-[#002777] hover:bg-blue-50 transition cursor-pointer"
            title="Exportar .docx"
          >
            <FileText className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => handleExport('xlsx')}
            className="p-1.5 rounded-lg text-slate-500 hover:text-emerald-700 hover:bg-emerald-50 transition cursor-pointer"
            title="Exportar .xlsx"
          >
            <FileSpreadsheet className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => handleExport('json')}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
            title="Exportar JSON"
          >
            <FileCode2 className="h-3.5 w-3.5" />
          </button>

          <div className="w-px h-5 bg-slate-200 mx-0.5" />

          {/* Download all */}
          <button
            type="button"
            onClick={() => handleExport('docx')}
            className="flex items-center gap-1 px-2 py-1 rounded-lg bg-[#002777] text-white text-[11px] font-semibold hover:bg-[#003399] transition cursor-pointer"
          >
            <Download className="h-3 w-3" />
            <span>Descargar</span>
          </button>

          {/* Collapse panel */}
          <button
            type="button"
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer ml-0.5"
            title="Ocultar panel"
          >
            <PanelRightClose className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Document Canvas */}
      <div className="flex-1 overflow-y-auto bg-slate-100/50">
        <div className="max-w-3xl mx-auto my-4 bg-white shadow-lg rounded-sm border border-slate-200 min-h-[600px]">
          {/* Document header */}
          <div className="border-b border-slate-200 px-8 py-5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#002777]">
              DOCUMENTO GENERADO
            </p>
            <h1 className="text-lg font-bold text-slate-900 font-serif mt-1">{title}</h1>
          </div>

          {/* Editable content area */}
          <div
            ref={editorRef}
            contentEditable
            suppressContentEditableWarning
            className="px-8 py-6 min-h-[500px] focus:outline-none text-slate-800 font-sans"
            onInput={(e) => {
              const text = (e.target as HTMLElement).innerText
              onContentChange(text)
            }}
            onBlur={onSave}
          >
            {renderDocumentContent()}
          </div>
        </div>
      </div>
    </div>
  )
}
