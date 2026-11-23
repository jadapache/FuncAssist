import {
  API_BASE,
  getAuthHeaders,
  handleResponse,
  type KnowledgeDocument,
} from '../../../api/client'

export type KnowledgePathResponse = {
  configured_path: string
  resolved_path: string
  is_custom: boolean
  is_accessible: boolean
  engine?: string
  pgvector_enabled?: boolean
  doc_count?: number
  chunk_count?: number
  ok?: boolean
}

export type KnowledgeIntegrityResponse = {
  ok: boolean
  details: string[]
  db_path: string
}

export type KnowledgeRebuildResponse = {
  ok: boolean
  chunks_reindexed: number
}

export type KnowledgeExportResponse = {
  ok: boolean
  manifest_path: string
  chunks_path: string
}

export const knowledgeApi = {
  listDocuments: () =>
    fetch(`${API_BASE}/api/knowledge/documents`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{ documents: KnowledgeDocument[] }>(r),
    ),

  uploadDocument: async (file: File, tags: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('tags', tags)
    return fetch(`${API_BASE}/api/knowledge/documents`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
      body: form,
    }).then((r) => handleResponse<{ document: KnowledgeDocument }>(r))
  },

  uploadDocumentsBatch: async (files: File[], tags: string) => {
    const form = new FormData()
    for (const file of files) {
      form.append('files', file)
    }
    form.append('tags', tags)
    return fetch(`${API_BASE}/api/knowledge/documents/batch`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
      body: form,
    }).then((r) => handleResponse<{ documents: KnowledgeDocument[]; errors: string[] }>(r))
  },

  deleteDocument: (id: string) =>
    fetch(`${API_BASE}/api/knowledge/documents/${id}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean }>(r)),

  retrieve: (query: string, sources: string[]) =>
    fetch(`${API_BASE}/api/knowledge/retrieve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ query, sources }),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getKnowledgePath: () =>
    fetch(`${API_BASE}/api/knowledge/path`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<KnowledgePathResponse>(r)),

  setKnowledgePath: (path: string) =>
    fetch(`${API_BASE}/api/knowledge/path`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ path }),
    }).then((r) => handleResponse<KnowledgePathResponse>(r)),

  checkIntegrity: () =>
    fetch(`${API_BASE}/api/knowledge/admin/integrity`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<KnowledgeIntegrityResponse>(r)),

  rebuildIndex: () =>
    fetch(`${API_BASE}/api/knowledge/admin/rebuild-index`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<KnowledgeRebuildResponse>(r)),

  exportJsonBackup: () =>
    fetch(`${API_BASE}/api/knowledge/admin/export-json`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<KnowledgeExportResponse>(r)),
}
