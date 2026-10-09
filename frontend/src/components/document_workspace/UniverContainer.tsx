/**
 * UniverContainer.tsx
 * High-performance visual document and spreadsheet canvas with Floating WYSIWYG Toolbar.
 * Supports both Template Builder mode and Artifact/Generated Document mode.
 * Eliminates paragraph outline boxes and helper texts in Artifact mode.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  FileText,
  FileSpreadsheet,
  Download,
  Eye,
  RefreshCw,
  Image as ImageIcon,
  Check,
  Tag,
  X,
  Plus,
  Trash2,
  Wand2,
} from 'lucide-react'
import type { UniverAdapter } from '../../document_agent/adapters/UniverAdapter'
import type { DocumentKind } from '../../document_agent/core/types'
import { UniverErrorBoundary } from './UniverErrorBoundary'
import { UniverFloatingToolbar } from './UniverFloatingToolbar'
import {
  validateTemplateContent,
  removeTagFromLine,
  autoFixTemplateIssues,
  type ValidationSummary,
} from './templateValidator'

export interface UniverContainerProps {
  adapter: UniverAdapter
  kind: DocumentKind
  title: string
  content: string
  headerContent?: string
  footerContent?: string
  images: Array<{ id: string; sectionId: string; url: string; caption?: string }>
  onInspect: () => void
  onExport: (format: 'docx' | 'xlsx' | 'json') => void
  onReloadFixture: () => void
  onContentChange?: (newContent: string) => void
  activeLineIndex?: number | null
  onActiveLineChange?: (lineIdx: number) => void
  hideHeader?: boolean
  availableTags?: string[]
  mode?: 'template' | 'artifact'
}

export type BlockType =
  | 'h1'
  | 'h2'
  | 'h3'
  | 'section-title'
  | 'bullet'
  | 'numbered'
  | 'quote'
  | 'table'
  | 'divider'
  | 'paragraph'
  | 'empty'

export interface ParsedBlock {
  id: string
  type: BlockType
  raw: string
  lineIndex: number
  tableData?: {
    header: string[]
    rows: string[][]
    headerLineIdx: number
    bodyLineIndices: number[]
  }
}

export const UniverContainer = (props: UniverContainerProps) => {
  return (
    <UniverErrorBoundary fallbackContent={props.content} onRecover={() => {}}>
      <UniverContainerInternal {...props} />
    </UniverErrorBoundary>
  )
}

const UniverContainerInternal = ({
  adapter,
  kind,
  title,
  content,
  headerContent,
  footerContent,
  images,
  onInspect,
  onExport,
  onReloadFixture,
  onContentChange,
  activeLineIndex,
  onActiveLineChange,
  hideHeader = false,
  availableTags = [],
  mode = 'template',
}: UniverContainerProps) => {
  const mountRef = useRef<HTMLDivElement>(null)

  // Floating Toolbar & Canvas State
  const [zoom, setZoom] = useState<number>(100)
  const [defaultFontFamily] = useState<string>('Inter')
  const [fontSize, setFontSize] = useState<number>(13)
  const [isBold, setIsBold] = useState<boolean>(false)
  const [isItalic, setIsItalic] = useState<boolean>(false)
  const [isUnderline, setIsUnderline] = useState<boolean>(false)
  const [textColor, setTextColor] = useState<string>('#0f172a')
  const [alignment, setAlignment] = useState<'left' | 'center' | 'right' | 'justify'>('left')
  const [blockFonts, setBlockFonts] = useState<Record<number, string>>({})

  // History stack for Undo / Redo
  const [history, setHistory] = useState<string[]>([content || ''])
  const [historyIdx, setHistoryIdx] = useState<number>(0)

  // Internal selection state
  const [internalActiveLine, setInternalActiveLine] = useState<number>(0)
  const [activeSheetTab, setActiveSheetTab] = useState('Casos de Prueba')

  const activeIdx = activeLineIndex !== undefined && activeLineIndex !== null ? activeLineIndex : internalActiveLine

  const currentFontFamily = blockFonts[activeIdx] || defaultFontFamily

  // Apply font family change specifically to selected line / block
  const handleFontFamilyChange = useCallback((newFont: string) => {
    setBlockFonts((prev) => ({
      ...prev,
      [activeIdx]: newFont,
    }))
  }, [activeIdx])

  // Attach adapter
  useEffect(() => {
    if (mountRef.current) {
      void adapter.attach(mountRef.current, { kind })
    }
    return () => {
      adapter.detach()
    }
  }, [adapter, kind])

  // Update content helper with history tracking
  const pushContentUpdate = useCallback(
    (newContent: string) => {
      if (!onContentChange) return
      onContentChange(newContent)
      setHistory((prev) => {
        const sliced = prev.slice(0, historyIdx + 1)
        if (sliced[sliced.length - 1] === newContent) return prev
        return [...sliced, newContent].slice(-30) // limit to 30 undo steps
      })
      setHistoryIdx((prev) => Math.min(prev + 1, 29))
    },
    [historyIdx, onContentChange]
  )

  const handleUndo = useCallback(() => {
    if (historyIdx > 0) {
      const prevIdx = historyIdx - 1
      const prevContent = history[prevIdx]
      setHistoryIdx(prevIdx)
      onContentChange?.(prevContent)
    }
  }, [history, historyIdx, onContentChange])

  const handleRedo = useCallback(() => {
    if (historyIdx < history.length - 1) {
      const nextIdx = historyIdx + 1
      const nextContent = history[nextIdx]
      setHistoryIdx(nextIdx)
      onContentChange?.(nextContent)
    }
  }, [history, historyIdx, onContentChange])

  // Focus tracking
  const handleLineFocus = useCallback(
    (lineIdx: number) => {
      setInternalActiveLine(lineIdx)
      onActiveLineChange?.(lineIdx)
    },
    [onActiveLineChange]
  )

  // Validation summary
  const validationSummary = useMemo<ValidationSummary>(() => {
    return validateTemplateContent(content, availableTags)
  }, [content, availableTags])

  // Update a single line in the markdown content
  const handleLineUpdate = useCallback(
    (lineIdx: number, newText: string) => {
      const lines = (content || '').split(/\r?\n/)
      lines[lineIdx] = newText
      pushContentUpdate(lines.join('\n'))
    },
    [content, pushContentUpdate]
  )

  // Remove a placeholder tag from a line cleanly without crashing
  const handleRemoveTag = useCallback(
    (lineIdx: number, tagToRemove: string) => {
      const lines = (content || '').split(/\r?\n/)
      const currentLine = lines[lineIdx] || ''
      const updated = removeTagFromLine(currentLine, tagToRemove)
      lines[lineIdx] = updated
      pushContentUpdate(lines.join('\n'))
    },
    [content, pushContentUpdate]
  )

  // Drag and drop tag handler
  const handleLineDrop = useCallback(
    (lineIdx: number, e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const droppedText = e.dataTransfer.getData('text/plain')
      if (droppedText && onContentChange) {
        const formattedTag = `{{${droppedText.replace(/[{}]/g, '').toUpperCase()}}}`
        const lines = (content || '').split(/\r?\n/)
        const targetLine = lines[lineIdx] || ''
        lines[lineIdx] = targetLine.trim() ? `${targetLine} ${formattedTag}` : formattedTag
        pushContentUpdate(lines.join('\n'))
        handleLineFocus(lineIdx)
      }
    },
    [content, onContentChange, pushContentUpdate, handleLineFocus]
  )

  // Auto-fix template syntax issues
  const handleAutoFix = useCallback(() => {
    const fixed = autoFixTemplateIssues(content)
    pushContentUpdate(fixed)
  }, [content, pushContentUpdate])

  // =========================================================================
  // PARSE DOCUMENT BLOCKS
  // =========================================================================
  const parsedBlocks = useMemo<ParsedBlock[]>(() => {
    const lines = (content || '').split(/\r?\n/)
    const blocks: ParsedBlock[] = []

    let inTable = false
    let tableRows: string[][] = []
    let tableIndices: number[] = []

    const flushTable = (endIdx: number) => {
      if (tableRows.length === 0) return
      const headerRow = tableRows[0]
      const bodyRows = tableRows.slice(1).filter((r) => !r.every((cell) => /^[\s:\-]*$/.test(cell)))
      const headerLineIdx = tableIndices[0]

      blocks.push({
        id: `table-${endIdx}`,
        type: 'table',
        raw: '',
        lineIndex: headerLineIdx,
        tableData: {
          header: headerRow,
          rows: bodyRows,
          headerLineIdx,
          bodyLineIndices: tableIndices.slice(1),
        },
      })

      tableRows = []
      tableIndices = []
      inTable = false
    }

    lines.forEach((line, idx) => {
      const trimmed = line.trim()

      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        inTable = true
        const cells = trimmed.split('|').slice(1, -1).map((c) => c.trim())
        tableRows.push(cells)
        tableIndices.push(idx)
      } else {
        if (inTable) {
          flushTable(idx)
        }

        if (!trimmed) {
          blocks.push({ id: `empty-${idx}`, type: 'empty', raw: line, lineIndex: idx })
        } else if (trimmed === '---' || trimmed === '***') {
          blocks.push({ id: `divider-${idx}`, type: 'divider', raw: line, lineIndex: idx })
        } else if (trimmed.startsWith('# ')) {
          blocks.push({ id: `h1-${idx}`, type: 'h1', raw: line, lineIndex: idx })
        } else if (trimmed.startsWith('## ')) {
          blocks.push({ id: `h2-${idx}`, type: 'h2', raw: line, lineIndex: idx })
        } else if (trimmed.startsWith('### ')) {
          blocks.push({ id: `h3-${idx}`, type: 'h3', raw: line, lineIndex: idx })
        } else if (
          /^\d+\.\s+[A-ZÁÉÍÓÚÑ\s]{4,}$/.test(trimmed) &&
          trimmed.length <= 80 &&
          !/[.,:;]$/.test(trimmed)
        ) {
          blocks.push({ id: `sectitle-${idx}`, type: 'section-title', raw: line, lineIndex: idx })
        } else if (
          trimmed.length >= 4 &&
          trimmed.length <= 65 &&
          trimmed === trimmed.toUpperCase() &&
          !/[.:,]$/.test(trimmed) &&
          !trimmed.startsWith('-') &&
          !trimmed.startsWith('*') &&
          !trimmed.startsWith('{{')
        ) {
          blocks.push({ id: `sectitle-${idx}`, type: 'section-title', raw: line, lineIndex: idx })
        } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          blocks.push({ id: `bullet-${idx}`, type: 'bullet', raw: line, lineIndex: idx })
        } else if (/^\d+\.\s/.test(trimmed)) {
          blocks.push({ id: `numbered-${idx}`, type: 'numbered', raw: line, lineIndex: idx })
        } else if (trimmed.startsWith('> ')) {
          blocks.push({ id: `quote-${idx}`, type: 'quote', raw: line, lineIndex: idx })
        } else {
          blocks.push({ id: `p-${idx}`, type: 'paragraph', raw: line, lineIndex: idx })
        }
      }
    })

    if (inTable) {
      flushTable(lines.length)
    }

    return blocks
  }, [content])

  // Active block currently selected
  const activeBlock = useMemo(() => {
    return parsedBlocks.find((b) => b.lineIndex === activeIdx) || parsedBlocks[0]
  }, [parsedBlocks, activeIdx])

  // Change active block type (H1, H2, H3, Bullet, Numbered, Quote, Paragraph)
  const handleChangeBlockType = (newType: string) => {
    if (!activeBlock) return
    const currentText = activeBlock.raw
    const cleanText = currentText.replace(/^[#0-9\.\-\*\>\s]+/, '').trim()
    let transformed = cleanText

    switch (newType) {
      case 'h1':
        transformed = `# ${cleanText}`
        break
      case 'h2':
        transformed = `## ${cleanText}`
        break
      case 'h3':
        transformed = `### ${cleanText}`
        break
      case 'bullet':
        transformed = `- ${cleanText}`
        break
      case 'numbered':
        transformed = `1. ${cleanText}`
        break
      case 'quote':
        transformed = `> ${cleanText}`
        break
      case 'paragraph':
      default:
        transformed = cleanText
        break
    }

    handleLineUpdate(activeBlock.lineIndex, transformed)
  }

  // Toggle Bullet List
  const handleToggleBulletList = () => {
    if (!activeBlock) return
    if (activeBlock.type === 'bullet') {
      handleChangeBlockType('paragraph')
    } else {
      handleChangeBlockType('bullet')
    }
  }

  // Toggle Numbered List
  const handleToggleNumberedList = () => {
    if (!activeBlock) return
    if (activeBlock.type === 'numbered') {
      handleChangeBlockType('paragraph')
    } else {
      handleChangeBlockType('numbered')
    }
  }

  // Indent / Outdent logic
  const handleIndent = () => {
    if (!activeBlock) return
    const currentText = activeBlock.raw
    const indented = `  ${currentText}`
    handleLineUpdate(activeBlock.lineIndex, indented)
  }

  // Outdent logic
  const handleOutdent = () => {
    if (!activeBlock) return
    const currentText = activeBlock.raw
    const outdented = currentText.replace(/^ {1,2}/, '')
    handleLineUpdate(activeBlock.lineIndex, outdented)
  }

  // Formatting toggles (Bold, Italic, Underline)
  const handleToggleBold = () => {
    setIsBold(!isBold)
    if (!activeBlock) return
    const currentText = activeBlock.raw
    if (!currentText) return
    const isAlreadyBold = currentText.includes('**')
    const updated = isAlreadyBold
      ? currentText.replace(/\*\*/g, '')
      : `**${currentText}**`
    handleLineUpdate(activeBlock.lineIndex, updated)
  }

  // Toggle Italic
  const handleToggleItalic = () => {
    setIsItalic(!isItalic)
    if (!activeBlock) return
    const currentText = activeBlock.raw
    if (!currentText) return
    const isAlreadyItalic = currentText.includes('*') && !currentText.includes('**')
    const updated = isAlreadyItalic
      ? currentText.replace(/\*/g, '')
      : `*${currentText}*`
    handleLineUpdate(activeBlock.lineIndex, updated)
  }

  const handleToggleUnderline = () => {
    setIsUnderline(!isUnderline)
  }

  // =========================================================================
  // INTERACTIVE TABLE OPERATIONS
  // =========================================================================
  const handleTableCellChange = (
    headerLineIdx: number,
    bodyIndices: number[],
    headerRow: string[],
    bodyRows: string[][],
    targetRowIdx: number,
    targetColIdx: number,
    newValue: string
  ) => {
    const lines = (content || '').split(/\r?\n/)

    if (targetRowIdx === -1) {
      const updatedHeader = [...headerRow]
      updatedHeader[targetColIdx] = newValue
      lines[headerLineIdx] = `| ${updatedHeader.join(' | ')} |`
    } else {
      const updatedRows = bodyRows.map((r, rIdx) => {
        if (rIdx !== targetRowIdx) return r
        const updated = [...r]
        updated[targetColIdx] = newValue
        return updated
      })
      const targetLine = bodyIndices[targetRowIdx]
      if (targetLine !== undefined) {
        lines[targetLine] = `| ${updatedRows[targetRowIdx].join(' | ')} |`
      }
    }

    pushContentUpdate(lines.join('\n'))
  }

  const handleAddTableRow = (
    headerLineIdx: number,
    bodyIndices: number[],
    headerRow: string[]
  ) => {
    const lines = (content || '').split(/\r?\n/)
    const emptyRow = new Array(headerRow.length).fill('-')
    const formattedRow = `| ${emptyRow.join(' | ')} |`

    const lastBodyIdx = bodyIndices.length > 0 ? bodyIndices[bodyIndices.length - 1] : headerLineIdx + 1
    lines.splice(lastBodyIdx + 1, 0, formattedRow)
    pushContentUpdate(lines.join('\n'))
  }

  const handleDeleteTableRow = (bodyIndices: number[], targetRowIdx: number) => {
    const lineToDelete = bodyIndices[targetRowIdx]
    if (lineToDelete === undefined) return
    const lines = (content || '').split(/\r?\n/)
    lines.splice(lineToDelete, 1)
    pushContentUpdate(lines.join('\n'))
  }

  const handleAddTableColumn = (
    headerLineIdx: number,
    bodyIndices: number[],
    headerRow: string[],
    bodyRows: string[][]
  ) => {
    const lines = (content || '').split(/\r?\n/)
    const updatedHeader = [...headerRow, `Columna ${headerRow.length + 1}`]
    lines[headerLineIdx] = `| ${updatedHeader.join(' | ')} |`

    const separatorIdx = headerLineIdx + 1
    if (lines[separatorIdx] && lines[separatorIdx].includes('---')) {
      const sepParts = new Array(updatedHeader.length).fill('---')
      lines[separatorIdx] = `| ${sepParts.join(' | ')} |`
    }

    bodyIndices.forEach((lineIdx, rIdx) => {
      const row = bodyRows[rIdx] || []
      const updated = [...row, '-']
      lines[lineIdx] = `| ${updated.join(' | ')} |`
    })

    pushContentUpdate(lines.join('\n'))
  }

  const handleDeleteTableColumn = (
    headerLineIdx: number,
    bodyIndices: number[],
    headerRow: string[],
    bodyRows: string[][],
    colIdx: number
  ) => {
    if (headerRow.length <= 1) return
    const lines = (content || '').split(/\r?\n/)
    const updatedHeader = headerRow.filter((_, idx) => idx !== colIdx)
    lines[headerLineIdx] = `| ${updatedHeader.join(' | ')} |`

    const separatorIdx = headerLineIdx + 1
    if (lines[separatorIdx] && lines[separatorIdx].includes('---')) {
      const sepParts = new Array(updatedHeader.length).fill('---')
      lines[separatorIdx] = `| ${sepParts.join(' | ')} |`
    }

    bodyIndices.forEach((lineIdx, rIdx) => {
      const row = bodyRows[rIdx] || []
      const updated = row.filter((_, idx) => idx !== colIdx)
      lines[lineIdx] = `| ${updated.join(' | ')} |`
    })

    pushContentUpdate(lines.join('\n'))
  }

  // =========================================================================
  // SPREADSHEET DATA & CELL EDITING (For XLSX kind)
  // =========================================================================
  const [spreadsheetRows, setSpreadsheetRows] = useState([
    { id: 'TC01', req: 'REQ-01', desc: 'Validar login con credenciales válidas', estado: 'Aprobado', severity: 'Alta' },
    { id: 'TC02', req: 'REQ-01', desc: 'Validar bloqueo tras 3 intentos fallidos', estado: 'Pendiente', severity: 'Crítica' },
    { id: 'TC03', req: 'REQ-02', desc: 'Validar carga de comprobante en PDF/PNG', estado: 'Aprobado', severity: 'Media' },
    { id: 'TC04', req: 'REQ-03', desc: 'Validar cálculo automático de retención', estado: 'En Ejecución', severity: 'Alta' },
    { id: 'TC05', req: 'REQ-04', desc: 'Verificar envío de notificación al usuario', estado: 'Pendiente', severity: 'Baja' },
  ])

  const handleSpreadsheetCellEdit = (idx: number, field: string, value: string) => {
    setSpreadsheetRows((prev) =>
      prev.map((row, rIdx) => (rIdx === idx ? { ...row, [field]: value } : row))
    )
  }

  // =========================================================================
  // RENDER BLOCKS (Rich formatted visual document with direct contentEditable)
  // =========================================================================
  const renderDocumentBlocks = () => {
    if (!content || !content.trim()) {
      return (
        <div
          onClick={() => {
            onContentChange?.('# NUEVO DOCUMENTO CORPORATIVO\n\nEscribe aquí el contenido del documento...')
          }}
          className="p-12 rounded-2xl border border-slate-200 bg-slate-50/60 hover:bg-blue-50/40 text-slate-500 text-center cursor-pointer transition space-y-2"
        >
          <FileText className="h-10 w-10 text-[#002777] mx-auto opacity-60" />
          <p className="font-semibold text-sm text-slate-700">El documento está vacío</p>
          <p className="text-xs text-slate-400">Haz clic aquí para comenzar a redactar.</p>
        </div>
      )
    }

    return (
      <div
        className="space-y-1 font-sans transition-all duration-200"
        style={{
          fontFamily: defaultFontFamily,
          fontSize: `${fontSize}px`,
          color: textColor,
          textAlign: alignment,
        }}
      >
        {parsedBlocks.map((block) => {
          const isActive = block.lineIndex === activeIdx

          // 1. RENDER TABLES
          if (block.type === 'table' && block.tableData) {
            const { header, rows, headerLineIdx, bodyLineIndices } = block.tableData
            const isTableActive = activeIdx === headerLineIdx || bodyLineIndices.includes(activeIdx)

            return (
              <div
                key={block.id}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => handleLineDrop(headerLineIdx, e)}
                className={`my-4 overflow-x-auto rounded-xl border border-slate-300 shadow-xs bg-white transition-all group/table ${
                  mode === 'template' && isTableActive ? 'ring-2 ring-blue-500/80 border-blue-400' : ''
                }`}
              >
                {/* Table Header Controls */}
                <div className="bg-slate-50 px-3 py-1.5 border-b border-slate-200 flex items-center justify-between text-[11px] text-slate-600">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[#002777]">Tabla Estructurada</span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {header.length} cols × {rows.length + 1} filas
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 opacity-90 group-hover/table:opacity-100 transition">
                    <button
                      type="button"
                      onClick={() => handleAddTableRow(headerLineIdx, bodyLineIndices, header)}
                      className="px-2 py-0.5 bg-white hover:bg-blue-50 text-[#002777] border border-blue-200 rounded font-semibold text-[10px] flex items-center gap-1 cursor-pointer shadow-2xs"
                      title="Agregar fila a la tabla"
                    >
                      <Plus className="h-3 w-3" />
                      <span>Fila</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleAddTableColumn(headerLineIdx, bodyLineIndices, header, rows)}
                      className="px-2 py-0.5 bg-white hover:bg-blue-50 text-[#002777] border border-blue-200 rounded font-semibold text-[10px] flex items-center gap-1 cursor-pointer shadow-2xs"
                      title="Agregar columna a la tabla"
                    >
                      <Plus className="h-3 w-3" />
                      <span>Columna</span>
                    </button>
                  </div>
                </div>

                <table className="w-full text-left border-collapse text-xs font-sans">
                  <thead>
                    <tr className="bg-[#002777] border-b border-blue-900 text-white font-bold">
                      {header.map((colName, cIdx) => (
                        <th key={cIdx} className="px-3 py-2 border-r border-blue-800/80 last:border-r-0 relative group/col">
                          <div className="flex items-center justify-between gap-1">
                            <input
                              type="text"
                              value={colName}
                              onChange={(e) =>
                                handleTableCellChange(headerLineIdx, bodyLineIndices, header, rows, -1, cIdx, e.target.value)
                              }
                              onFocus={() => handleLineFocus(headerLineIdx)}
                              className="w-full bg-transparent text-white font-bold focus:outline-hidden focus:bg-blue-900/60 rounded px-1 py-0.5"
                            />
                            {header.length > 1 && (
                              <button
                                type="button"
                                onClick={() => handleDeleteTableColumn(headerLineIdx, bodyLineIndices, header, rows, cIdx)}
                                className="opacity-0 group-hover/col:opacity-100 p-0.5 hover:bg-red-500/80 rounded text-blue-200 hover:text-white transition cursor-pointer"
                                title="Eliminar columna"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            )}
                          </div>
                        </th>
                      ))}
                      <th className="w-8 px-1 py-2 text-center bg-[#002777]" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, rIdx) => {
                      const lineIdx = bodyLineIndices[rIdx] || headerLineIdx
                      return (
                        <tr
                          key={rIdx}
                          className={`group/row transition-colors ${
                            rIdx % 2 === 0 ? 'bg-white' : 'bg-slate-50/70'
                          } hover:bg-blue-50/40`}
                        >
                          {row.map((cellValue, cIdx) => (
                            <td key={cIdx} className="px-3 py-1.5 border-t border-r border-slate-200 last:border-r-0 text-slate-700">
                              <input
                                type="text"
                                value={cellValue}
                                onChange={(e) =>
                                  handleTableCellChange(headerLineIdx, bodyLineIndices, header, rows, rIdx, cIdx, e.target.value)
                                }
                                onFocus={() => handleLineFocus(lineIdx)}
                                className="w-full bg-transparent text-xs text-slate-800 focus:outline-hidden focus:bg-white focus:ring-1 focus:ring-blue-400 rounded px-1 py-0.5"
                              />
                            </td>
                          ))}
                          <td className="w-8 px-1 py-1.5 border-t border-slate-200 text-center">
                            <button
                              type="button"
                              onClick={() => handleDeleteTableRow(bodyLineIndices, rIdx)}
                              className="opacity-0 group-hover/row:opacity-100 p-1 hover:bg-red-50 hover:text-red-600 rounded text-slate-400 transition cursor-pointer"
                              title="Eliminar fila"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )
          }

          // 2. RENDER FORMATTED BLOCKS WITH DIRECT CONTENTEDITABLE
          const trimmed = block.raw.trim()

          const blockStyleClass =
            mode === 'artifact'
              ? 'my-1 py-0.5 px-1 rounded-sm cursor-text transition-colors hover:bg-slate-100/40'
              : `group/block relative my-0.5 py-1 px-2 rounded-lg cursor-text transition-all border ${
                  isActive
                    ? 'bg-blue-50/40 border-blue-300 shadow-2xs'
                    : 'border-transparent hover:bg-slate-100/70 hover:border-slate-200'
                }`

          return (
            <div
              key={block.id}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleLineDrop(block.lineIndex, e)}
              onClick={(e) => {
                handleLineFocus(block.lineIndex)
                if (e.target === e.currentTarget) {
                  const editable = e.currentTarget.querySelector<HTMLElement>('[contenteditable="true"]')
                  if (editable) {
                    editable.focus()
                  }
                }
              }}
              className={blockStyleClass}
            >
              {block.type === 'empty' && (
                <div
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = htmlToMarkdown(e.currentTarget.innerHTML)
                    handleLineUpdate(block.lineIndex, text)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = htmlToMarkdown(e.currentTarget.innerHTML)
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = text
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    fontSize: `${fontSize}px`,
                    color: textColor,
                    textAlign: alignment,
                    minHeight: mode === 'template' ? '1.75rem' : '0.75rem',
                  }}
                  data-placeholder="+ Espacio en blanco (Clic para escribir)"
                  className={`text-slate-700 leading-relaxed text-xs md:text-[13px] outline-none focus:bg-blue-50/40 rounded px-1.5 py-0.5 my-0.5 transition-colors ${
                    mode === 'template'
                      ? 'min-h-[1.75rem] empty:before:content-[attr(data-placeholder)] empty:before:text-slate-400 empty:before:italic empty:before:text-[11px] empty:before:opacity-80 hover:empty:before:opacity-100 focus:empty:before:opacity-30 empty:before:pointer-events-none empty:before:select-none'
                      : 'min-h-[0.75rem]'
                  }`}
                />
              )}

              {block.type === 'divider' && <hr className="my-3 border-slate-200 select-none" />}

              {block.type === 'h1' && (
                <h1
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = e.currentTarget.innerText
                    handleLineUpdate(block.lineIndex, `# ${text}`)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = e.currentTarget.innerText
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = `# ${text}`
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    color: textColor || '#002777',
                    textAlign: alignment,
                  }}
                  className="text-lg md:text-xl font-bold text-[#002777] border-b border-[#002777]/30 pb-1.5 mt-4 mb-2 font-serif outline-none focus:bg-blue-50/30 rounded px-1"
                >
                  {renderRichInlineText(trimmed.replace(/^#\s*/, ''), block.lineIndex, handleRemoveTag, mode)}
                </h1>
              )}

              {block.type === 'h2' && (
                <h2
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = e.currentTarget.innerText
                    handleLineUpdate(block.lineIndex, `## ${text}`)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = e.currentTarget.innerText
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = `## ${text}`
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    color: textColor || '#002777',
                    textAlign: alignment,
                  }}
                  className="text-sm md:text-base font-bold text-[#002777] border-b border-[#002777]/25 pb-1 mt-3 mb-1.5 uppercase tracking-wide outline-none focus:bg-blue-50/30 rounded px-1"
                >
                  {renderRichInlineText(trimmed.replace(/^##\s*/, ''), block.lineIndex, handleRemoveTag, mode)}
                </h2>
              )}

              {block.type === 'h3' && (
                <h3
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = e.currentTarget.innerText
                    handleLineUpdate(block.lineIndex, `### ${text}`)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = e.currentTarget.innerText
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = `### ${text}`
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    color: textColor || '#002777',
                    textAlign: alignment,
                  }}
                  className="text-xs md:text-sm font-bold text-[#002777] border-b border-slate-200 pb-0.5 mt-2.5 mb-1 uppercase tracking-wide outline-none focus:bg-blue-50/30 rounded px-1"
                >
                  {renderRichInlineText(trimmed.replace(/^###\s*/, ''), block.lineIndex, handleRemoveTag, mode)}
                </h3>
              )}

              {block.type === 'section-title' && (
                <h2
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = e.currentTarget.innerText
                    handleLineUpdate(block.lineIndex, text)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = e.currentTarget.innerText
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = text
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    color: textColor || '#002777',
                    textAlign: alignment,
                  }}
                  className="text-xs md:text-sm font-bold text-[#002777] border-b border-[#002777]/25 pb-0.5 mt-3 mb-1 uppercase tracking-wide outline-none focus:bg-blue-50/30 rounded px-1"
                >
                  {renderRichInlineText(trimmed, block.lineIndex, handleRemoveTag, mode)}
                </h2>
              )}

              {block.type === 'bullet' && (
                <div className="flex items-start gap-2.5 ml-3 my-0.5 text-slate-700 leading-relaxed text-xs">
                  <span className="text-[#002777] font-bold text-base leading-none select-none">•</span>
                  <div
                    contentEditable
                    suppressContentEditableWarning
                    onFocus={() => handleLineFocus(block.lineIndex)}
                    onBlur={(e) => {
                      const text = htmlToMarkdown(e.currentTarget.innerHTML)
                      handleLineUpdate(block.lineIndex, `- ${text}`)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        const text = htmlToMarkdown(e.currentTarget.innerHTML)
                        const lines = (content || '').split(/\r?\n/)
                        if (!text.trim()) {
                          lines[block.lineIndex] = ''
                        } else {
                          lines[block.lineIndex] = `- ${text}`
                          lines.splice(block.lineIndex + 1, 0, '- ')
                        }
                        pushContentUpdate(lines.join('\n'))
                        handleLineFocus(block.lineIndex + 1)
                      }
                    }}
                    style={{
                      fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                      fontSize: `${fontSize}px`,
                      color: textColor,
                      textAlign: alignment,
                    }}
                    className="flex-1 outline-none focus:bg-blue-50/30 rounded px-1"
                  >
                    {renderRichInlineText(trimmed.replace(/^[-*]\s*/, ''), block.lineIndex, handleRemoveTag, mode)}
                  </div>
                </div>
              )}

              {block.type === 'numbered' && (
                <div className="flex items-start gap-2 ml-3 my-0.5 text-slate-700 leading-relaxed text-xs">
                  <div
                    contentEditable
                    suppressContentEditableWarning
                    onFocus={() => handleLineFocus(block.lineIndex)}
                    onBlur={(e) => {
                      const text = htmlToMarkdown(e.currentTarget.innerHTML)
                      handleLineUpdate(block.lineIndex, text)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        const text = htmlToMarkdown(e.currentTarget.innerHTML)
                        const lines = (content || '').split(/\r?\n/)
                        lines[block.lineIndex] = text
                        lines.splice(block.lineIndex + 1, 0, '')
                        pushContentUpdate(lines.join('\n'))
                        handleLineFocus(block.lineIndex + 1)
                      }
                    }}
                    style={{
                      fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                      fontSize: `${fontSize}px`,
                      color: textColor,
                      textAlign: alignment,
                    }}
                    className="flex-1 outline-none focus:bg-blue-50/30 rounded px-1"
                  >
                    {renderRichInlineText(trimmed, block.lineIndex, handleRemoveTag, mode)}
                  </div>
                </div>
              )}

              {block.type === 'quote' && (
                <blockquote
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = htmlToMarkdown(e.currentTarget.innerHTML)
                    handleLineUpdate(block.lineIndex, `> ${text}`)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = htmlToMarkdown(e.currentTarget.innerHTML)
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = `> ${text}`
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    fontSize: `${fontSize}px`,
                    color: textColor,
                    textAlign: alignment,
                  }}
                  className="border-l-4 border-blue-500 bg-blue-50/50 p-3 rounded-r-xl my-2 text-slate-700 italic text-xs leading-relaxed outline-none focus:ring-1 focus:ring-blue-400"
                >
                  {renderRichInlineText(trimmed.slice(2), block.lineIndex, handleRemoveTag, mode)}
                </blockquote>
              )}

              {block.type === 'paragraph' && (
                <div
                  contentEditable
                  suppressContentEditableWarning
                  onFocus={() => handleLineFocus(block.lineIndex)}
                  onBlur={(e) => {
                    const text = htmlToMarkdown(e.currentTarget.innerHTML)
                    handleLineUpdate(block.lineIndex, text)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = htmlToMarkdown(e.currentTarget.innerHTML)
                      const lines = (content || '').split(/\r?\n/)
                      lines[block.lineIndex] = text
                      lines.splice(block.lineIndex + 1, 0, '')
                      pushContentUpdate(lines.join('\n'))
                      handleLineFocus(block.lineIndex + 1)
                    }
                  }}
                  style={{
                    fontFamily: blockFonts[block.lineIndex] || defaultFontFamily,
                    fontSize: `${fontSize}px`,
                    color: textColor,
                    textAlign: alignment,
                  }}
                  className="text-slate-700 leading-relaxed text-xs md:text-[13px] outline-none focus:bg-blue-50/30 rounded px-1 my-0.5"
                >
                  {renderRichInlineText(block.raw, block.lineIndex, handleRemoveTag, mode)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col bg-slate-200/60 overflow-hidden border-0">
      {/* 1. Top Workspace Header Bar (Shown when hideHeader is false) */}
      {!hideHeader && (
        <div className="bg-white px-5 py-2.5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 shrink-0 shadow-2xs">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-xl text-white ${kind === 'spreadsheet' ? 'bg-emerald-600' : 'bg-[#002777]'}`}>
              {kind === 'spreadsheet' ? <FileSpreadsheet className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-slate-900 text-sm">{title}</h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase bg-blue-50 text-[#002777] border border-blue-200">
                  Univer Runtime
                </span>
                {mode === 'template' && validationSummary.isValid && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                    <Check className="h-3 w-3" />
                    <span>{validationSummary.totalPlaceholders} tags</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {mode === 'template' && !validationSummary.isValid && validationSummary.issues.some((i) => i.autoFixable) && (
              <button
                type="button"
                onClick={handleAutoFix}
                className="px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-900 rounded-lg text-xs font-semibold border border-amber-300 flex items-center gap-1.5 transition cursor-pointer"
              >
                <Wand2 className="h-3.5 w-3.5 text-amber-700" />
                <span>Auto-corregir Tags</span>
              </button>
            )}

            <button
              type="button"
              onClick={onInspect}
              className="px-3 py-1.5 bg-slate-50 hover:bg-blue-50 hover:text-[#002777] text-slate-700 rounded-lg text-xs font-semibold border border-slate-200 flex items-center gap-1.5 transition cursor-pointer"
            >
              <Eye className="h-4 w-4 text-[#002777]" />
              <span>Inspeccionar</span>
            </button>

            <button
              type="button"
              onClick={onReloadFixture}
              className="px-3 py-1.5 bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold border border-slate-200 flex items-center gap-1.5 transition cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5 text-slate-500" />
              <span>Recargar</span>
            </button>

            <div className="h-4 w-px bg-slate-200 mx-1" />

            <button
              type="button"
              onClick={() => onExport(kind === 'spreadsheet' ? 'xlsx' : 'docx')}
              className="px-3.5 py-1.5 bg-[#002777] hover:bg-[#003399] text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-xs transition cursor-pointer"
            >
              <Download className="h-3.5 w-3.5" />
              <span>Exportar {kind === 'spreadsheet' ? 'XLSX' : 'DOCX'}</span>
            </button>
          </div>
        </div>
      )}

      {/* 2. MAIN DOCUMENT / SPREADSHEET CANVAS VIEWPORT */}
      <div className="relative flex-1 overflow-y-auto p-4 md:p-6 flex flex-col items-center justify-start">
        {/* FLOATING WYSIWYG TOOLBAR (Sticky floating pill directly over canvas) */}
        {kind === 'document' && (
          <div className="sticky top-2 z-30 mb-3 w-full max-w-4xl flex justify-center pointer-events-none shrink-0 px-2">
            <div className="pointer-events-auto w-full flex justify-center">
              <UniverFloatingToolbar
                zoom={zoom}
                onZoomChange={setZoom}
                canUndo={historyIdx > 0}
                canRedo={historyIdx < history.length - 1}
                onUndo={handleUndo}
                onRedo={handleRedo}
                textStyle={activeBlock ? activeBlock.type : 'paragraph'}
                onTextStyleChange={handleChangeBlockType}
                fontFamily={currentFontFamily}
                onFontFamilyChange={handleFontFamilyChange}
                fontSize={fontSize}
                onFontSizeChange={setFontSize}
                isBold={isBold}
                onToggleBold={handleToggleBold}
                isItalic={isItalic}
                onToggleItalic={handleToggleItalic}
                isUnderline={isUnderline}
                onToggleUnderline={handleToggleUnderline}
                textColor={textColor}
                onTextColorChange={setTextColor}
                alignment={alignment}
                onAlignmentChange={setAlignment}
                onToggleBulletList={handleToggleBulletList}
                onToggleNumberedList={handleToggleNumberedList}
                onIndent={handleIndent}
                onOutdent={handleOutdent}
                mode={mode}
              />
            </div>
          </div>
        )}

        {kind === 'document' ? (
          /* DOCX Viewport (A4 Paper Canvas with Zoom scaling) */
          <div
            style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}
            className="transition-transform duration-200 ease-out w-full max-w-4xl"
          >
            <div
              ref={mountRef}
              className="bg-white shadow-xl border border-slate-300 rounded-sm p-8 md:p-14 min-h-[850px] space-y-6 text-slate-800 font-sans transition-all"
            >
              {/* Header Content Section */}
              {headerContent ? (
                <div className="border-b-2 border-slate-200 pb-3 mb-5 space-y-1 select-none">
                  <div className="flex items-center justify-between text-[10px] font-bold text-[#002777] uppercase tracking-wider">
                    <span>ENCABEZADO DE DOCUMENTO CORPORATIVO</span>
                    <span className="font-mono font-semibold text-slate-400">Word / PDF Header</span>
                  </div>
                  <div className="p-1 text-xs text-slate-600">{renderStaticMarkdownBlocks(headerContent)}</div>
                </div>
              ) : null}

              {/* Document Body Blocks */}
              <div className="space-y-0.5 text-xs leading-relaxed font-sans">{renderDocumentBlocks()}</div>

              {/* Footer Content Section */}
              {footerContent ? (
                <div className="border-t-2 border-slate-200 pt-3 mt-6 space-y-1 select-none">
                  <div className="flex items-center justify-between text-[10px] font-bold text-[#002777] uppercase tracking-wider">
                    <span>PIE DE PÁGINA CORPORATIVO</span>
                    <span className="font-mono font-semibold text-slate-400">Word / PDF Footer</span>
                  </div>
                  <div className="p-1 text-xs text-slate-600">{renderStaticMarkdownBlocks(footerContent)}</div>
                </div>
              ) : null}

              {/* Evidence Images */}
              {images.length > 0 && (
                <div className="mt-6 pt-4 border-t border-slate-200 select-none">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-2">
                    <ImageIcon className="h-4 w-4 text-emerald-600" />
                    Evidencias Insertadas ({images.length})
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {images.map((img) => (
                      <div
                        key={img.id}
                        className="group relative bg-slate-50 border border-slate-200 rounded-xl p-3 shadow-xs hover:border-indigo-300 transition-all"
                      >
                        <div className="h-44 bg-slate-200/80 rounded-lg flex items-center justify-center overflow-hidden border border-slate-300/80">
                          {img.url ? (
                            <img
                              src={img.url}
                              alt={img.caption || 'Evidencia'}
                              className="h-full w-full object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = 'none'
                              }}
                            />
                          ) : null}
                          <div className="flex flex-col items-center justify-center p-4 text-center">
                            <ImageIcon className="h-8 w-8 text-slate-400 mb-1" />
                            <span className="font-semibold text-xs text-slate-700">{img.id}</span>
                            <span className="text-[11px] text-slate-500 mt-0.5">{img.caption || 'Evidencia adjunta'}</span>
                          </div>
                        </div>
                        <div className="mt-2 flex items-center justify-between text-[11px]">
                          <span className="font-mono text-indigo-700 font-semibold">{img.caption || img.id}</span>
                          <span className="text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-sm font-semibold flex items-center gap-1">
                            <Check className="h-3 w-3" /> Insertada
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* XLSX Spreadsheet Viewport */
          <div
            ref={mountRef}
            className="bg-white w-full max-w-5xl shadow-md border border-slate-200 rounded-lg flex flex-col min-h-[600px] overflow-hidden"
          >
            {/* Formula Bar */}
            <div className="bg-slate-50 border-b border-slate-200 px-4 py-2 flex items-center gap-3 text-xs">
              <span className="font-mono font-bold text-slate-500 bg-white px-2 py-0.5 border border-slate-200 rounded-sm">
                C4
              </span>
              <span className="font-mono text-slate-400 font-bold">fx</span>
              <input
                type="text"
                readOnly
                value="=SUMA(D2:D10)"
                className="flex-1 bg-white border border-slate-200 px-3 py-1 rounded-sm font-mono text-slate-700 text-xs"
              />
            </div>

            {/* Spreadsheet Grid Table */}
            <div className="flex-1 overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 font-mono">
                    <th className="w-10 p-2 text-center border-r border-slate-200 bg-slate-200/60">#</th>
                    <th className="p-2 border-r border-slate-200">A (ID Caso)</th>
                    <th className="p-2 border-r border-slate-200">B (Requerimiento)</th>
                    <th className="p-2 border-r border-slate-200">C (Descripción de Prueba)</th>
                    <th className="p-2 border-r border-slate-200">D (Estado)</th>
                    <th className="p-2">E (Severidad)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 font-sans">
                  {spreadsheetRows.map((row, idx) => (
                    <tr key={row.id} className="hover:bg-blue-50/50">
                      <td className="p-2 text-center font-mono text-slate-400 bg-slate-50 border-r border-slate-200">
                        {idx + 1}
                      </td>
                      <td className="p-2 font-mono font-bold text-indigo-700 border-r border-slate-200">
                        <input
                          type="text"
                          value={row.id}
                          onChange={(e) => handleSpreadsheetCellEdit(idx, 'id', e.target.value)}
                          className="w-full bg-transparent focus:outline-hidden focus:bg-white focus:ring-1 focus:ring-indigo-500 rounded-xs px-1"
                        />
                      </td>
                      <td className="p-2 font-semibold text-slate-800 border-r border-slate-200">
                        <input
                          type="text"
                          value={row.req}
                          onChange={(e) => handleSpreadsheetCellEdit(idx, 'req', e.target.value)}
                          className="w-full bg-transparent focus:outline-hidden focus:bg-white focus:ring-1 focus:ring-indigo-500 rounded-xs px-1"
                        />
                      </td>
                      <td className="p-2 text-slate-700 border-r border-slate-200">
                        <input
                          type="text"
                          value={row.desc}
                          onChange={(e) => handleSpreadsheetCellEdit(idx, 'desc', e.target.value)}
                          className="w-full bg-transparent focus:outline-hidden focus:bg-white focus:ring-1 focus:ring-indigo-500 rounded-xs px-1"
                        />
                      </td>
                      <td className="p-2 border-r border-slate-200">
                        <select
                          value={row.estado}
                          onChange={(e) => handleSpreadsheetCellEdit(idx, 'estado', e.target.value)}
                          className="bg-transparent text-xs font-semibold rounded-md px-1 py-0.5 border border-slate-200 focus:outline-hidden focus:bg-white"
                        >
                          <option value="Aprobado">Aprobado</option>
                          <option value="Pendiente">Pendiente</option>
                          <option value="En Ejecución">En Ejecución</option>
                        </select>
                      </td>
                      <td className="p-2 font-semibold text-slate-700">
                        <select
                          value={row.severity}
                          onChange={(e) => handleSpreadsheetCellEdit(idx, 'severity', e.target.value)}
                          className="bg-transparent text-xs font-semibold rounded-md px-1 py-0.5 border border-slate-200 focus:outline-hidden focus:bg-white"
                        >
                          <option value="Alta">Alta</option>
                          <option value="Crítica">Crítica</option>
                          <option value="Media">Media</option>
                          <option value="Baja">Baja</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Sheets Tabs Bottom Bar */}
            <div className="bg-slate-100 border-t border-slate-200 px-4 py-1.5 flex items-center gap-1">
              {['Casos de Prueba', 'Estimaciones', 'Matriz de Trazabilidad'].map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveSheetTab(tab)}
                  className={`px-3 py-1 text-xs font-semibold rounded-t-md transition-colors ${
                    activeSheetTab === tab
                      ? 'bg-white text-emerald-700 shadow-2xs border-t-2 border-emerald-600'
                      : 'text-slate-600 hover:bg-slate-200/60'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// HELPER: RICH INLINE TEXT RENDERING WITH REMOVABLE TAG CHIPS
function renderRichInlineText(
  text: string,
  lineIndex: number,
  onRemoveTag?: (lineIdx: number, tag: string) => void,
  mode: 'template' | 'artifact' = 'template'
) {
  if (!text) return null
  const parts = text.split(/(\{\{[A-Za-z0-9_\-.]+\}\}|\*\*.*?\*\*|_.*?_|\*.*?\*)/g)

  return parts.map((part, i) => {
    if (part.startsWith('{{') && part.endsWith('}}')) {
      const cleanName = part.replace(/[{}]/g, '')
      return (
        <span
          key={`tag-${lineIndex}-${i}`}
          className="inline-flex items-center gap-1 px-2.5 py-0.5 mx-1 rounded-full text-xs font-mono font-bold bg-blue-100 text-[#002777] border border-blue-300 shadow-2xs select-none hover:bg-blue-200 transition group/badge"
          title={`Placeholder: ${part}`}
        >
          <Tag className="h-3 w-3 text-[#002777] shrink-0" />
          <span>{part}</span>
          {mode === 'template' && onRemoveTag && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onRemoveTag(lineIndex, cleanName)
              }}
              className="ml-0.5 text-blue-400 hover:text-red-600 hover:bg-blue-300/60 rounded-full p-0.5 transition cursor-pointer"
              title={`Eliminar placeholder ${part}`}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      )
    }

    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className="font-bold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      )
    }

    if (
      (part.startsWith('*') && part.endsWith('*')) ||
      (part.startsWith('_') && part.endsWith('_'))
    ) {
      return (
        <em key={i} className="italic text-slate-800">
          {part.slice(1, -1)}
        </em>
      )
    }

    return <React.Fragment key={i}>{part}</React.Fragment>
  })
}

// Helper: Convert contentEditable HTML back to clean Markdown
function htmlToMarkdown(html: string): string {
  if (typeof document === 'undefined') return html
  const tempDiv = document.createElement('div')
  tempDiv.innerHTML = html

  // Replace <strong> and <b> with **text**
  tempDiv.querySelectorAll('strong, b').forEach((el) => {
    const text = el.textContent || ''
    el.replaceWith(`**${text}**`)
  })

  // Replace <em> and <i> with *text*
  tempDiv.querySelectorAll('em, i').forEach((el) => {
    const text = el.textContent || ''
    el.replaceWith(`*${text}*`)
  })

  return tempDiv.textContent || ''
}

// Static markdown block renderer for header/footer
function renderStaticMarkdownBlocks(rawText: string) {
  const lines = rawText.split(/\r?\n/)
  return (
    <div className="space-y-1">
      {lines.map((line, idx) => {
        const trimmed = line.trim()
        if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
          const cells = trimmed.split('|').slice(1, -1).map((c) => c.trim())
          if (cells.every((c) => /^[:\-\s]+$/.test(c))) return null
          return (
            <div key={idx} className="flex border border-slate-200 rounded text-[11px] bg-slate-50 divide-x divide-slate-200">
              {cells.map((cell, cIdx) => (
                <div key={cIdx} className="p-1.5 flex-1 font-medium text-slate-700">
                  {renderRichInlineText(cell, idx)}
                </div>
              ))}
            </div>
          )
        }
        if (!trimmed) return <div key={idx} className="h-2" />
        return (
          <p key={idx} className="text-slate-600">
            {renderRichInlineText(line, idx)}
          </p>
        )
      })}
    </div>
  )
}
