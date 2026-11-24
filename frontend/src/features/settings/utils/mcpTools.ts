import type { McpToolApprovalInput } from '../types'

export type McpToolDraft = {
  name: string
  description: string
  inputSchema: string
  readOnly: boolean
}

export type McpToolApprovalResult =
  | { ok: true; tool: McpToolApprovalInput }
  | { ok: false; error: string }

export const buildToolApproval = (draft: McpToolDraft): McpToolApprovalResult => {
  const name = draft.name.trim()
  if (!name) return { ok: false, error: 'El nombre de la herramienta es obligatorio.' }

  const tool: McpToolApprovalInput = {
    name,
    description: draft.description.trim(),
    read_only: draft.readOnly,
    approved: true,
  }

  const rawSchema = draft.inputSchema.trim()
  if (rawSchema) {
    let parsed: unknown
    try {
      parsed = JSON.parse(rawSchema)
    } catch {
      return { ok: false, error: 'El esquema de entrada no es un JSON válido.' }
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { ok: false, error: 'El esquema de entrada debe ser un objeto JSON.' }
    }
    tool.input_schema = parsed as Record<string, unknown>
  }

  return { ok: true, tool }
}

export const buildToolRevocation = (name: string): McpToolApprovalInput => ({
  name,
  approved: false,
})
