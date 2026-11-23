/**
 * univer-blocks.ts
 * Framework-agnostic types and pure helpers moved out of React `UniverContainer.tsx`
 * (block parsing, rich inline tokenisation, contentEditable HTML → Markdown, static header/footer lines).
 * Export names match the React module so imports can be ported 1:1.
 */

import type { UniverAdapter } from '../agent/adapters/UniverAdapter'
import type { DocumentKind } from '../agent/core/types'

/** Same shape as the React props. In Angular the `onX` callbacks are `output()`s of `UniverContainerComponent`. */
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

export type UniverImage = UniverContainerProps['images'][number]

export type UniverMode = 'template' | 'artifact'

export type UniverAlignment = 'left' | 'center' | 'right' | 'justify'

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

// =========================================================================
// PARSE DOCUMENT BLOCKS (verbatim port of the React `parsedBlocks` useMemo)
// =========================================================================
export function parseDocumentBlocks(content: string): ParsedBlock[] {
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
}

/**
 * Text that the React JSX passed to `renderRichInlineText(...)` for each editable block type.
 * (h1/h2/h3 strip the hashes, bullets strip the marker, quotes drop `> `, paragraphs keep the raw line.)
 */
export function getBlockInlineText(block: ParsedBlock): string {
  const trimmed = block.raw.trim()
  switch (block.type) {
    case 'h1':
      return trimmed.replace(/^#\s*/, '')
    case 'h2':
      return trimmed.replace(/^##\s*/, '')
    case 'h3':
      return trimmed.replace(/^###\s*/, '')
    case 'section-title':
      return trimmed
    case 'bullet':
      return trimmed.replace(/^[-*]\s*/, '')
    case 'numbered':
      return trimmed
    case 'quote':
      return trimmed.slice(2)
    case 'paragraph':
      return block.raw
    default:
      return ''
  }
}

// =========================================================================
// RICH INLINE TEXT TOKENS (placeholder chips, **bold**, *italic* / _italic_)
// =========================================================================
export type RichInlinePart =
  /** `text` is the full `{{NAME}}` token, `name` the token without braces. */
  | { kind: 'tag'; text: string; name: string }
  /** `text` is the inner text (markers removed). */
  | { kind: 'strong'; text: string }
  | { kind: 'em'; text: string }
  | { kind: 'text'; text: string }

/** Tokenisation used by React `renderRichInlineText` (same regex and branch order). */
export function splitRichInlineText(text: string): RichInlinePart[] {
  if (!text) return []
  const parts = text.split(/(\{\{[A-Za-z0-9_\-.]+\}\}|\*\*.*?\*\*|_.*?_|\*.*?\*)/g)

  return parts.map((part): RichInlinePart => {
    if (part.startsWith('{{') && part.endsWith('}}')) {
      return { kind: 'tag', text: part, name: part.replace(/[{}]/g, '') }
    }

    if (part.startsWith('**') && part.endsWith('**')) {
      return { kind: 'strong', text: part.slice(2, -2) }
    }

    if ((part.startsWith('*') && part.endsWith('*')) || (part.startsWith('_') && part.endsWith('_'))) {
      return { kind: 'em', text: part.slice(1, -1) }
    }

    return { kind: 'text', text: part }
  })
}

// Helper: Convert contentEditable HTML back to clean Markdown
export function htmlToMarkdown(html: string): string {
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

// =========================================================================
// STATIC MARKDOWN LINES (header / footer renderer)
// =========================================================================
export type StaticMarkdownLine =
  | { kind: 'table'; cells: string[] }
  /** Table separator row: React returned `null` (nothing rendered). */
  | { kind: 'hidden' }
  | { kind: 'spacer' }
  | { kind: 'text'; line: string }

/** Line classification used by React `renderStaticMarkdownBlocks`. */
export function parseStaticMarkdownLines(rawText: string): StaticMarkdownLine[] {
  const lines = rawText.split(/\r?\n/)
  return lines.map((line): StaticMarkdownLine => {
    const trimmed = line.trim()
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed.split('|').slice(1, -1).map((c) => c.trim())
      if (cells.every((c) => /^[:\-\s]+$/.test(c))) return { kind: 'hidden' }
      return { kind: 'table', cells }
    }
    if (!trimmed) return { kind: 'spacer' }
    return { kind: 'text', line }
  })
}
