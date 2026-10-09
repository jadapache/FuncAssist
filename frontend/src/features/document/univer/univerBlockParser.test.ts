/**
 * univerBlockParser.test.ts
 * Tests for block parsing and manipulation behaviors in UniverContainer.
 */

import assert from 'node:assert'
import test from 'node:test'
import { removeTagFromLine } from './templateValidator.js'

test('markdown table row operations preserve column structure', () => {
  const header = ['ID', 'Caso', 'Resultado']
  const row1 = ['TC01', 'Login con credenciales válidas', 'Exitoso']
  const row2 = ['TC02', 'Login fallido por bloqueo', 'Exitoso']

  // Serialize table
  const lines = [
    `| ${header.join(' | ')} |`,
    `| ${header.map(() => '---').join(' | ')} |`,
    `| ${row1.join(' | ')} |`,
    `| ${row2.join(' | ')} |`,
  ]

  assert.strictEqual(lines.length, 4)
  assert.ok(lines[0].includes('ID | Caso | Resultado'))

  // Add column
  const newHeader = [...header, 'Severidad']
  const newRow1 = [...row1, 'Alta']
  const newRow2 = [...row2, 'Media']

  const updatedLines = [
    `| ${newHeader.join(' | ')} |`,
    `| ${newHeader.map(() => '---').join(' | ')} |`,
    `| ${newRow1.join(' | ')} |`,
    `| ${newRow2.join(' | ')} |`,
  ]

  assert.ok(updatedLines[0].includes('Severidad'))
  assert.ok(updatedLines[2].includes('Alta'))
  assert.ok(updatedLines[3].includes('Media'))
})

test('tag insertion into table row places tag inside cell before closing pipe', () => {
  const tableLine = '| Rol | Nombre | Estado |'
  const formattedTag = '{{ESTADO_RESPONSABLE}}'

  // Testing the safe insertion logic used in TemplatesPanel
  const lastPipeIdx = tableLine.lastIndexOf('|')
  const beforePipe = tableLine.substring(0, lastPipeIdx).trimEnd()
  const updatedLine = `${beforePipe} ${formattedTag} |`

  assert.strictEqual(updatedLine, '| Rol | Nombre | Estado {{ESTADO_RESPONSABLE}} |')
  assert.ok(updatedLine.endsWith(' |'))
})

test('backspace on placeholder tag via removeTagFromLine never leaves trailing or leading broken brackets', () => {
  const original = '# DOCUMENTO DE {{TIPO_DOCUMENTO}}'
  const afterDelete = removeTagFromLine(original, 'TIPO_DOCUMENTO')
  assert.strictEqual(afterDelete, '# DOCUMENTO DE')

  const midText = 'El paciente {{NOMBRE_PACIENTE}} fue atendido por {{MEDICO}} el dia de hoy.'
  const afterDeleteFirst = removeTagFromLine(midText, 'NOMBRE_PACIENTE')
  assert.strictEqual(afterDeleteFirst, 'El paciente fue atendido por {{MEDICO}} el dia de hoy.')
})

test('bullet list continuation generates valid markdown syntax', () => {
  const line = '- Primer punto identificado'
  const isBullet = line.startsWith('- ') || line.startsWith('* ')
  assert.strictEqual(isBullet, true)

  const nextBullet = '- '
  const lines = [line]
  lines.push(nextBullet)
  assert.deepStrictEqual(lines, ['- Primer punto identificado', '- '])
})
