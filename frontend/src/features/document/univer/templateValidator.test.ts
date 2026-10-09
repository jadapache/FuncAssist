/**
 * templateValidator.test.ts
 * Comprehensive test suite for templateValidator functions.
 */

import assert from 'node:assert'
import test from 'node:test'
import {
  extractPlaceholders,
  validateTemplateContent,
  removeTagFromLine,
  autoFixTemplateIssues,
} from './templateValidator.js'

test('extractPlaceholders extracts unique uppercase tags', () => {
  const text = 'Responsable: {{RESPONSABLE}}, Fecha: {{fecha}}, Tag2: {{RESPONSABLE}}'
  const tags = extractPlaceholders(text)
  assert.deepStrictEqual(tags, ['RESPONSABLE', 'FECHA'])
})

test('validateTemplateContent detects empty document', () => {
  const res = validateTemplateContent('')
  assert.strictEqual(res.isValid, false)
  assert.strictEqual(res.issues.length, 1)
  assert.strictEqual(res.issues[0].id, 'empty_content')
})

test('validateTemplateContent detects unclosed tags', () => {
  const text = 'Este es un texto con un tag sin cerrar: {{TAG_INVALIDO'
  const res = validateTemplateContent(text)
  assert.strictEqual(res.isValid, false)
  const unclosed = res.issues.find((i) => i.id.startsWith('unclosed_tag'))
  assert.ok(unclosed, 'Should find unclosed tag issue')
})

test('validateTemplateContent detects empty tags {{}}', () => {
  const text = 'Tag vacio aqui: {{}} en el texto'
  const res = validateTemplateContent(text)
  assert.strictEqual(res.isValid, false)
  const emptyTag = res.issues.find((i) => i.id.startsWith('empty_tag'))
  assert.ok(emptyTag, 'Should find empty tag issue')
})

test('validateTemplateContent detects space in tags and suggests fix', () => {
  const text = 'Tag con espacio: {{MI TAG CON ESPACIOS}}'
  const res = validateTemplateContent(text)
  const spaceIssue = res.issues.find((i) => i.id.startsWith('space_tag'))
  assert.ok(spaceIssue, 'Should find space tag issue')
  assert.strictEqual(spaceIssue?.suggestion, '{{MI_TAG_CON_ESPACIOS}}')
})

test('validateTemplateContent distinguishes system and custom tags', () => {
  const text = '{{FECHA}} y {{MI_TAG_CUSTOM}}'
  const res = validateTemplateContent(text, ['FECHA', 'RESPONSABLE'])
  assert.deepStrictEqual(res.systemPlaceholders, ['FECHA'])
  assert.deepStrictEqual(res.customPlaceholders, ['MI_TAG_CUSTOM'])
})

test('removeTagFromLine cleanly removes placeholder without leaving double spaces', () => {
  const line = 'Responsable del proyecto: {{RESPONSABLE}} en revisión'
  const clean = removeTagFromLine(line, 'RESPONSABLE')
  assert.strictEqual(clean, 'Responsable del proyecto: en revisión')

  const lineWithBrackets = 'Fecha: {{FECHA}}'
  const clean2 = removeTagFromLine(lineWithBrackets, '{{FECHA}}')
  assert.strictEqual(clean2, 'Fecha:')
})

test('autoFixTemplateIssues fixes spaces and unclosed tags at line ends', () => {
  const broken = 'Item 1: {{TAG CON ESPACIOS}}\nItem 2: {{TAG_SIN_CERRAR'
  const fixed = autoFixTemplateIssues(broken)
  assert.ok(fixed.includes('{{TAG_CON_ESPACIOS}}'))
  assert.ok(fixed.includes('{{TAG_SIN_CERRAR}}'))
})

test('validateTemplateContent validates table column counts', () => {
  const tableText = `| Col1 | Col2 | Col3 |
| --- | --- | --- |
| Val1 | Val2 |`
  const res = validateTemplateContent(tableText)
  const tableIssue = res.issues.find((i) => i.id.startsWith('table_cols'))
  assert.ok(tableIssue, 'Should find table column mismatch issue')
})
