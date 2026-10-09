/**
 * templateValidator.ts
 * Validation and auto-correction engine for templates, placeholders, and markdown structures.
 */

export interface ValidationIssue {
  id: string
  type: 'error' | 'warning' | 'info'
  message: string
  lineIndex?: number
  suggestion?: string
  autoFixable?: boolean
}

export interface ValidationSummary {
  isValid: boolean
  totalPlaceholders: number
  uniquePlaceholders: string[]
  systemPlaceholders: string[]
  customPlaceholders: string[]
  tableCount: number
  sectionCount: number
  issues: ValidationIssue[]
}

const TAG_REGEX = /\{\{([A-Za-z0-9_\-.]+)\}\}/g
const SPACE_TAG_REGEX = /\{\{([A-Za-z0-9_\-.]+\s+[A-Za-z0-9_\-.\s]*)\}\}/g

export function extractPlaceholders(text: string): string[] {
  if (!text) return []
  const matches = text.match(TAG_REGEX)
  if (!matches) return []
  return Array.from(new Set(matches.map((m) => m.replace(/[{}]/g, '').toUpperCase())))
}

export function validateTemplateContent(
  content: string,
  knownSystemTags: string[] = []
): ValidationSummary {
  const issues: ValidationIssue[] = []
  const normalizedSystemTags = new Set(knownSystemTags.map((t) => t.replace(/[{}]/g, '').toUpperCase()))

  if (!content || !content.trim()) {
    issues.push({
      id: 'empty_content',
      type: 'warning',
      message: 'El documento está vacío. Agrega contenido o estructura para comenzar.',
    })
    return {
      isValid: false,
      totalPlaceholders: 0,
      uniquePlaceholders: [],
      systemPlaceholders: [],
      customPlaceholders: [],
      tableCount: 0,
      sectionCount: 0,
      issues,
    }
  }

  const lines = content.split(/\r?\n/)
  const discoveredTags: string[] = []
  let tableCount = 0
  let inTable = false
  let tableHeaderCols = 0
  let sectionCount = 0

  lines.forEach((line, idx) => {
    const trimmed = line.trim()

    // 1. Detect Headings
    if (
      trimmed.startsWith('# ') ||
      trimmed.startsWith('## ') ||
      trimmed.startsWith('### ') ||
      /^[0-9]+\.\s+[A-ZÁÉÍÓÚÑ\s]{4,}$/.test(trimmed)
    ) {
      sectionCount++
    }

    // 2. Validate Placeholders in line
    const matches = line.match(TAG_REGEX)
    if (matches) {
      for (const m of matches) {
        discoveredTags.push(m.replace(/[{}]/g, '').toUpperCase())
      }
    }

    // Check for empty placeholder {{}}
    if (line.includes('{{}}')) {
      issues.push({
        id: `empty_tag_${idx}`,
        type: 'error',
        message: `Línea ${idx + 1}: Placeholder vacío "{{}}" detectado. Debe contener un identificador.`,
        lineIndex: idx,
        autoFixable: true,
      })
    }

    // Check for placeholders with spaces e.g. {{MI TAG}}
    const spaceMatches = line.match(SPACE_TAG_REGEX)
    if (spaceMatches) {
      for (const sm of spaceMatches) {
        const clean = sm.replace(/[{}]/g, '').trim().replace(/\s+/g, '_').toUpperCase()
        issues.push({
          id: `space_tag_${idx}_${clean}`,
          type: 'warning',
          message: `Línea ${idx + 1}: El placeholder "${sm}" contiene espacios. Se recomienda usar guiones bajos "{{${clean}}}".`,
          lineIndex: idx,
          suggestion: `{{${clean}}}`,
          autoFixable: true,
        })
      }
    }

    // Check for unclosed placeholders: {{TAG without }}
    // Find occurrences of '{{' not followed by '}}' on the same line
    const openIdx = line.indexOf('{{')
    if (openIdx !== -1) {
      const closeIdx = line.indexOf('}}', openIdx)
      if (closeIdx === -1) {
        issues.push({
          id: `unclosed_tag_${idx}`,
          type: 'error',
          message: `Línea ${idx + 1}: Tag "{{..." no cerrado correctamente con "}}".`,
          lineIndex: idx,
          autoFixable: true,
        })
      }
    }

    // 3. Validate Markdown Tables
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed.split('|').slice(1, -1).map((c) => c.trim())
      if (!inTable) {
        inTable = true
        tableCount++
        tableHeaderCols = cells.length
      } else {
        // Body row or separator
        const isSeparator = cells.every((c) => /^[:\-\s]+$/.test(c))
        if (!isSeparator && cells.length !== tableHeaderCols) {
          issues.push({
            id: `table_cols_${idx}`,
            type: 'warning',
            message: `Línea ${idx + 1}: La fila de la tabla tiene ${cells.length} columnas pero la cabecera tiene ${tableHeaderCols}.`,
            lineIndex: idx,
          })
        }
      }
    } else {
      inTable = false
    }
  })

  const uniquePlaceholders = Array.from(new Set(discoveredTags))
  const systemPlaceholders = uniquePlaceholders.filter((t) => normalizedSystemTags.has(t))
  const customPlaceholders = uniquePlaceholders.filter((t) => !normalizedSystemTags.has(t))

  return {
    isValid: issues.filter((i) => i.type === 'error').length === 0,
    totalPlaceholders: discoveredTags.length,
    uniquePlaceholders,
    systemPlaceholders,
    customPlaceholders,
    tableCount,
    sectionCount,
    issues,
  }
}

/**
 * Safely removes a specific tag from a line without breaking markdown syntax or leaving double spaces.
 */
export function removeTagFromLine(line: string, tagToRemove: string): string {
  if (!line) return ''
  const cleanTag = tagToRemove.replace(/[{}]/g, '').trim().toUpperCase()
  const regex = new RegExp(`\\{\\{${cleanTag}\\}\\}`, 'gi')
  const updated = line.replace(regex, '').replace(/\s{2,}/g, ' ').trim()
  return updated
}

/**
 * Safely auto-fixes syntax issues in template markdown.
 */
export function autoFixTemplateIssues(content: string): string {
  if (!content) return ''
  const lines = content.split(/\r?\n/)

  const fixedLines = lines.map((line) => {
    let result = line

    // Remove empty {{}}
    result = result.replace(/\{\{\s*\}\}/g, '')

    // Fix spaces in tags: {{TAG WITH SPACES}} -> {{TAG_WITH_SPACES}}
    result = result.replace(SPACE_TAG_REGEX, (_, inner: string) => {
      const sanitized = inner.trim().replace(/\s+/g, '_').toUpperCase()
      return `{{${sanitized}}}`
    })

    // Fix unclosed tag at end of line: {{TAG -> {{TAG}}
    if (result.includes('{{') && !result.includes('}}')) {
      const match = result.match(/\{\{([A-Za-z0-9_]+)$/)
      if (match) {
        result = `${result}}}`
      }
    }

    return result
  })

  return fixedLines.join('\n')
}
