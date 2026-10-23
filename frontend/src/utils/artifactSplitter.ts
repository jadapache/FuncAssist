export interface ExtractedArtifact {
  title: string
  extension: 'docx' | 'xlsx' | 'txt'
  content: string
}

/**
 * Normalizes text lines to compare structural signatures across templates and responses.
 */
function normalizeLine(line: string): string {
  return line
    .replace(/\{\{[^}]+\}\}/g, '') // remove placeholders
    .replace(/[#*`_|\-:[\]]/g, ' ') // remove markdown syntax
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

/**
 * Extracts a candidate structural signature from a template.
 * Looks for:
 * 1. The first Markdown heading (e.g., "# Formato ...", "## 1. ...")
 * 2. Or the first non-empty structural line (e.g. table header, "Código Requerimiento:", etc.)
 */
function extractTemplateSignature(templateContent?: string): { signatureLine: string; isHeading: boolean } | null {
  if (!templateContent) return null

  const lines = templateContent.split(/\r?\n/)
  for (const raw of lines) {
    const trimmed = raw.trim()
    if (!trimmed) continue

    // If it's a heading
    if (trimmed.startsWith('#')) {
      const normalized = normalizeLine(trimmed)
      if (normalized.length >= 4) {
        return { signatureLine: normalized, isHeading: true }
      }
    }

    // If it's a table header line like "|  | FORMATO ... |"
    if (trimmed.startsWith('|') && !trimmed.includes('---')) {
      const normalized = normalizeLine(trimmed)
      if (normalized.length >= 6) {
        return { signatureLine: normalized, isHeading: false }
      }
    }

    // If it's a key line like "Código Requerimiento:" or "Objetivo:"
    const norm = normalizeLine(trimmed)
    if (norm.length >= 8 && !norm.includes('---')) {
      return { signatureLine: norm, isHeading: false }
    }
  }

  return null
}

/**
 * Attempts to extract a sensible, human-readable document title from an artifact text block.
 */
function extractBlockTitle(blockText: string, fallbackTitle: string, index: number): string {
  const lines = blockText.split(/\r?\n/)

  // 1. Look for explicit module or requirement patterns
  for (const l of lines) {
    const line = l.trim()
    const moduleMatch = line.match(/(?:m[óo]dulo|funcionalidad|dominio|requerimiento|mejora)[:\s*]+([^\n|]+)/i)
    if (moduleMatch && moduleMatch[1]) {
      const cleaned = moduleMatch[1].replace(/[*`_]/g, '').trim()
      if (cleaned.length > 2 && !cleaned.includes('{{')) {
        return cleaned
      }
    }
  }

  // 2. Look for table cell mentioning Módulo / Funcionalidad: [Nombre]
  const tableCellMatch = blockText.match(/\|\s*([^|\n]*(?:Compras|Inventario|Reabastecimiento|Mejora|M[óo]dulo|ERP)[^|\n]*)\s*\|/i)
  if (tableCellMatch && tableCellMatch[1]) {
    const val = tableCellMatch[1].replace(/[*`_#]/g, '').trim()
    if (val.length > 4 && !val.includes('---') && !val.includes('Fecha')) {
      return val
    }
  }

  // 3. Look for the first H1 or H2
  for (const l of lines) {
    const line = l.trim()
    if (line.startsWith('# ') || line.startsWith('## ')) {
      const titleCandidate = line.replace(/^#+\s*/, '').replace(/[*`_]/g, '').trim()
      if (titleCandidate && titleCandidate.length > 3 && !titleCandidate.toLowerCase().includes('formato')) {
        return titleCandidate
      }
    }
  }

  return `${fallbackTitle} (Parte ${index + 1})`
}

/**
 * Parses raw text from the AI response and detects multi-artifact structures.
 * Supports:
 * 1. XML-style <artifact title="..." extension="...">...</artifact> tags
 * 2. Canonical template signature repeats (agnostic to any template!)
 * 3. Repetition of major markdown headings (# or ##)
 */
export function parseMultipleArtifacts(
  rawText: string,
  defaultTitle: string,
  defaultExtension: 'docx' | 'xlsx' | 'txt' = 'docx',
  templateContent?: string,
  allowPlainTextFallback = true,
): ExtractedArtifact[] {
  if (!rawText || !rawText.trim()) return []

  const artifacts: ExtractedArtifact[] = []

  // =========================================================================
  // Strategy 1: Explicit <artifact title="..." extension="..."> tags
  // Supports streaming in-progress tags (closing tag optional at stream end)
  // =========================================================================
  const xmlArtifactRegex =
    /<artifact\s+title=["']([^"']+)["'](?:\s+extension=["']([^"']+)["'])?\s*>([\s\S]*?)(?:<\/artifact>|(?=<artifact)|$)/gi

  let xmlMatch: RegExpExecArray | null

  while ((xmlMatch = xmlArtifactRegex.exec(rawText)) !== null) {
    const title = xmlMatch[1].trim()
    const extension = (xmlMatch[2]?.toLowerCase() as 'docx' | 'xlsx' | 'txt') || defaultExtension
    let content = xmlMatch[3].trim()
    content = content.replace(/<\/artifact>?$/i, '').trim()
    if (content || xmlMatch[0].length > 20) {
      artifacts.push({ title, extension, content })
    }
  }

  // Return early only if we matched explicit tags
  if (artifacts.length > 0 && rawText.includes('<artifact')) {
    return artifacts
  }



  // =========================================================================
  // Strategy 2: Template Signature Match (Agnostic to ANY template)
  // When a template repeats its opening signature (header, table, or initial line),
  // each occurrence marks the start of a new artifact.
  // =========================================================================
  const tmplSig = extractTemplateSignature(templateContent)
  if (tmplSig) {
    const lines = rawText.split(/\r?\n/)
    const splitIndices: number[] = []

    for (let i = 0; i < lines.length; i++) {
      const norm = normalizeLine(lines[i])
      if (norm && (norm === tmplSig.signatureLine || norm.includes(tmplSig.signatureLine) || tmplSig.signatureLine.includes(norm))) {
        // Avoid splitting on adjacent lines of the same block
        if (splitIndices.length === 0 || i - splitIndices[splitIndices.length - 1] > 8) {
          splitIndices.push(i)
        }
      }
    }

    if (splitIndices.length > 1) {
      for (let idx = 0; idx < splitIndices.length; idx++) {
        const start = splitIndices[idx]
        const end = idx + 1 < splitIndices.length ? splitIndices[idx + 1] : lines.length
        const blockContent = lines.slice(start, end).join('\n').trim()

        if (blockContent.length > 80) {
          const title = extractBlockTitle(blockContent, defaultTitle, idx)
          artifacts.push({
            title,
            extension: defaultExtension,
            content: blockContent,
          })
        }
      }

      if (artifacts.length > 1) {
        return artifacts
      }
    }
  }

  // =========================================================================
  // Strategy 3: Multi-document repetition via Markdown delimiters or repeated # / ##
  // E.g. "# Documento 1:", "## 1. Información", repeated top-level headings
  // =========================================================================
  const lines = rawText.split(/\r?\n/)
  const firstHeadingLine = lines.find((l) => l.trim().startsWith('#'))
  if (firstHeadingLine) {
    const firstHeadingNorm = normalizeLine(firstHeadingLine)
    const headingSplitIndices: number[] = []

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim()
      if (line.startsWith('#')) {
        const norm = normalizeLine(line)
        // If the exact same opening title re-appears or lines explicitly declare a new Document / Mejora
        if (
          norm === firstHeadingNorm ||
          /^(?:#+\s*(?:documento|mejora|requerimiento|punto)\s*\d*)/i.test(line)
        ) {
          if (headingSplitIndices.length === 0 || i - headingSplitIndices[headingSplitIndices.length - 1] > 8) {
            headingSplitIndices.push(i)
          }
        }
      }
    }

    if (headingSplitIndices.length > 1) {
      for (let idx = 0; idx < headingSplitIndices.length; idx++) {
        const start = headingSplitIndices[idx]
        const end = idx + 1 < headingSplitIndices.length ? headingSplitIndices[idx + 1] : lines.length
        const blockContent = lines.slice(start, end).join('\n').trim()

        if (blockContent.length > 80) {
          const title = extractBlockTitle(blockContent, defaultTitle, idx)
          artifacts.push({
            title,
            extension: defaultExtension,
            content: blockContent,
          })
        }
      }

      if (artifacts.length > 1) {
        return artifacts
      }
    }
  }

  // =========================================================================
  // Fallback: Single artifact return (only if allowPlainTextFallback is true)
  // =========================================================================
  if (!allowPlainTextFallback) {
    return []
  }

  return [
    {
      title: defaultTitle,
      extension: defaultExtension,
      content: rawText,
    },
  ]
}

export interface ParsedAgenticStream {
  chatText: string
  artifacts: ExtractedArtifact[]
  isConversational: boolean
}

export function parseStreamForChatAndArtifacts(
  rawText: string,
  defaultTitle: string,
  defaultExtension: 'docx' | 'xlsx' | 'txt' = 'docx',
  templateContent?: string,
): ParsedAgenticStream {
  if (!rawText || !rawText.trim()) {
    return { chatText: '', artifacts: [], isConversational: true }
  }

  const hasXmlArtifact = /<artifact[\s>]/i.test(rawText)

  if (hasXmlArtifact) {
    const artifacts = parseMultipleArtifacts(rawText, defaultTitle, defaultExtension, templateContent, false)
    const chatText = rawText
      .replace(/<artifact\s+title=["'][^"']+["'](?:\s+extension=["'][^"']+["'])?\s*>[\s\S]*?(?:<\/artifact>|$)/gi, '')
      .trim()
    return {
      chatText,
      artifacts,
      isConversational: false,
    }
  }

  return {
    chatText: rawText,
    artifacts: [],
    isConversational: true,
  }
}

/**
 * Genera un subtítulo descriptivo para un artefacto a partir de su contenido.
 * Toma el primer párrafo de texto real (no heading, no tabla, no código).
 */
export function generateArtifactSubtitle(content: string, maxLength = 80): string {
  if (!content) return ''
  const lines = content.split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue
    if (trimmed.startsWith('#')) continue       // skip headings
    if (trimmed.startsWith('|')) continue       // skip table rows
    if (trimmed.startsWith('```')) continue     // skip code fences
    if (trimmed.startsWith('-') && trimmed.length < 4) continue  // skip lone dashes
    const clean = trimmed.replace(/[*_`]/g, '').trim()
    if (clean.length > 10) {
      return clean.length > maxLength ? `${clean.slice(0, maxLength)}…` : clean
    }
  }
  return ''
}

