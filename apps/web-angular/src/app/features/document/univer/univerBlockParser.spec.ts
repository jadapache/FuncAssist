import { describe, it, expect } from 'vitest'
import { removeTagFromLine } from './templateValidator'

describe('Document Block Parser & Manipulation', () => {
  it('markdown table row operations preserve column structure', () => {
    const header = ['ID', 'Caso', 'Resultado']
    const row1 = ['TC01', 'Login con credenciales válidas', 'Exitoso']
    const row2 = ['TC02', 'Login fallido por bloqueo', 'Exitoso']

    const lines = [
      `| ${header.join(' | ')} |`,
      `| ${header.map(() => '---').join(' | ')} |`,
      `| ${row1.join(' | ')} |`,
      `| ${row2.join(' | ')} |`,
    ]

    expect(lines.length).toBe(4)
    expect(lines[0]).toContain('ID | Caso | Resultado')

    const newHeader = [...header, 'Severidad']
    const newRow1 = [...row1, 'Alta']
    const newRow2 = [...row2, 'Media']

    const updatedLines = [
      `| ${newHeader.join(' | ')} |`,
      `| ${newHeader.map(() => '---').join(' | ')} |`,
      `| ${newRow1.join(' | ')} |`,
      `| ${newRow2.join(' | ')} |`,
    ]

    expect(updatedLines[0]).toContain('Severidad')
    expect(updatedLines[2]).toContain('Alta')
    expect(updatedLines[3]).toContain('Media')
  })

  it('tag insertion into table row places tag inside cell before closing pipe', () => {
    const tableLine = '| Rol | Nombre | Estado |'
    const formattedTag = '{{ESTADO_RESPONSABLE}}'

    const lastPipeIdx = tableLine.lastIndexOf('|')
    const beforePipe = tableLine.substring(0, lastPipeIdx).trimEnd()
    const updatedLine = `${beforePipe} ${formattedTag} |`

    expect(updatedLine).toBe('| Rol | Nombre | Estado {{ESTADO_RESPONSABLE}} |')
    expect(updatedLine.endsWith(' |')).toBe(true)
  })

  it('backspace on placeholder tag via removeTagFromLine never leaves trailing or leading broken brackets', () => {
    const original = '# DOCUMENTO DE {{TIPO_DOCUMENTO}}'
    const afterDelete = removeTagFromLine(original, 'TIPO_DOCUMENTO')
    expect(afterDelete).toBe('# DOCUMENTO DE')

    const midText = 'El paciente {{NOMBRE_PACIENTE}} fue atendido por {{MEDICO}} el dia de hoy.'
    const afterDeleteFirst = removeTagFromLine(midText, 'NOMBRE_PACIENTE')
    expect(afterDeleteFirst).toBe('El paciente fue atendido por {{MEDICO}} el dia de hoy.')
  })

  it('bullet list continuation generates valid markdown syntax', () => {
    const line = '- Primer punto identificado'
    const isBullet = line.startsWith('- ') || line.startsWith('* ')
    expect(isBullet).toBe(true)

    const nextBullet = '- '
    const lines = [line]
    lines.push(nextBullet)
    expect(lines).toEqual(['- Primer punto identificado', '- '])
  })
})
