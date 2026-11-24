import { describe, expect, it } from 'vitest'
import { buildToolApproval, buildToolRevocation } from '../utils/mcpTools'

const draft = { name: ' search ', description: ' Busca ', inputSchema: '', readOnly: false }

describe('buildToolApproval', () => {
  it('construye la aprobación sin solo lectura por defecto', () => {
    expect(buildToolApproval(draft)).toEqual({
      ok: true,
      tool: { name: 'search', description: 'Busca', read_only: false, approved: true },
    })
  })

  it('incluye el esquema de entrada cuando es un objeto JSON', () => {
    const result = buildToolApproval({ ...draft, inputSchema: '{"type":"object"}', readOnly: true })
    expect(result).toEqual({
      ok: true,
      tool: {
        name: 'search',
        description: 'Busca',
        read_only: true,
        approved: true,
        input_schema: { type: 'object' },
      },
    })
  })

  it('rechaza nombre vacío, JSON inválido y esquemas que no son objeto', () => {
    expect(buildToolApproval({ ...draft, name: ' ' }).ok).toBe(false)
    expect(buildToolApproval({ ...draft, inputSchema: '{' }).ok).toBe(false)
    expect(buildToolApproval({ ...draft, inputSchema: '[1]' }).ok).toBe(false)
  })
})

describe('buildToolRevocation', () => {
  it('marca la herramienta como no aprobada', () => {
    expect(buildToolRevocation('search')).toEqual({ name: 'search', approved: false })
  })
})
