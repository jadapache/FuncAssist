import { describe, it, expect } from 'vitest'
import {
  extractPlaceholders,
  validateTemplateContent,
  removeTagFromLine,
  autoFixTemplateIssues,
} from './templateValidator'

describe('Document Template Validator', () => {
  it('extractPlaceholders extracts unique uppercase tags', () => {
    const text = 'Responsable: {{RESPONSABLE}}, Fecha: {{fecha}}, Tag2: {{RESPONSABLE}}'
    const tags = extractPlaceholders(text)
    expect(tags).toEqual(['RESPONSABLE', 'FECHA'])
  })

  it('validateTemplateContent detects empty document', () => {
    const res = validateTemplateContent('')
    expect(res.isValid).toBe(false)
    expect(res.issues.length).toBe(1)
    expect(res.issues[0].id).toBe('empty_content')
  })

  it('validateTemplateContent detects unclosed tags', () => {
    const text = 'Este es un texto con un tag sin cerrar: {{TAG_INVALIDO'
    const res = validateTemplateContent(text)
    expect(res.isValid).toBe(false)
    const unclosed = res.issues.find((i) => i.id.startsWith('unclosed_tag'))
    expect(unclosed).toBeDefined()
  })

  it('validateTemplateContent detects empty tags {{}}', () => {
    const text = 'Tag vacio aqui: {{}} en el texto'
    const res = validateTemplateContent(text)
    expect(res.isValid).toBe(false)
    const emptyTag = res.issues.find((i) => i.id.startsWith('empty_tag'))
    expect(emptyTag).toBeDefined()
  })

  it('validateTemplateContent detects space in tags and suggests fix', () => {
    const text = 'Tag con espacio: {{MI TAG CON ESPACIOS}}'
    const res = validateTemplateContent(text)
    const spaceIssue = res.issues.find((i) => i.id.startsWith('space_tag'))
    expect(spaceIssue).toBeDefined()
    expect(spaceIssue?.suggestion).toBe('{{MI_TAG_CON_ESPACIOS}}')
  })

  it('validateTemplateContent distinguishes system and custom tags', () => {
    const text = '{{FECHA}} y {{MI_TAG_CUSTOM}}'
    const res = validateTemplateContent(text, ['FECHA', 'RESPONSABLE'])
    expect(res.systemPlaceholders).toEqual(['FECHA'])
    expect(res.customPlaceholders).toEqual(['MI_TAG_CUSTOM'])
  })

  it('removeTagFromLine cleanly removes placeholder without leaving double spaces', () => {
    const line = 'Responsable del proyecto: {{RESPONSABLE}} en revisión'
    const clean = removeTagFromLine(line, 'RESPONSABLE')
    expect(clean).toBe('Responsable del proyecto: en revisión')

    const lineWithBrackets = 'Fecha: {{FECHA}}'
    const clean2 = removeTagFromLine(lineWithBrackets, '{{FECHA}}')
    expect(clean2).toBe('Fecha:')
  })

  it('autoFixTemplateIssues fixes spaces and unclosed tags at line ends', () => {
    const broken = 'Item 1: {{TAG CON ESPACIOS}}\nItem 2: {{TAG_SIN_CERRAR'
    const fixed = autoFixTemplateIssues(broken)
    expect(fixed).toContain('{{TAG_CON_ESPACIOS}}')
    expect(fixed).toContain('{{TAG_SIN_CERRAR}}')
  })

  it('validateTemplateContent validates table column counts', () => {
    const tableText = `| Col1 | Col2 | Col3 |
| --- | --- | --- |
| Val1 | Val2 |`
    const res = validateTemplateContent(tableText)
    const tableIssue = res.issues.find((i) => i.id.startsWith('table_cols'))
    expect(tableIssue).toBeDefined()
  })
})
