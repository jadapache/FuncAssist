import { API_BASE, getAuthHeaders } from '../../../api/client'
import type { Artifact } from '../../../types/artifacts'

/**
 * Download logic shared verbatim by React `InlineArtifactCard` and `ArtifactModal`
 * (.txt generated locally; .docx/.xlsx exported by the backend).
 * Resolves with the success toast message; rejects when the export fails.
 */
export async function downloadArtifact(artifact: Artifact): Promise<string> {
  const { title, content, extension } = artifact

  if (extension === 'txt') {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title.replace(/\s+/g, '_')}.txt`
    a.click()
    URL.revokeObjectURL(url)
    return 'Documento descargado como .txt'
  }

  const endpoint =
    extension === 'xlsx' ? `${API_BASE}/api/doc-agent/export-xlsx` : `${API_BASE}/api/doc-agent/export-docx`

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ title, content }),
  })

  if (!response.ok) throw new Error(`Error al exportar .${extension}`)

  const arrayBuffer = await response.arrayBuffer()
  const mimeType =
    extension === 'xlsx'
      ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

  const blob = new Blob([arrayBuffer], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title.replace(/\s+/g, '_')}.${extension}`
  a.click()
  URL.revokeObjectURL(url)
  return `Documento descargado como .${extension}`
}

/** Approximate size label used by `InlineArtifactCard` ("Estimar tamaño aproximado basado en caracteres"). */
export function formatApproxSize(text: string): string {
  const bytes = new Blob([text]).size
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
