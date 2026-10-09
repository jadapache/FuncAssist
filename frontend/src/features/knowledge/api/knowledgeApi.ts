import { API_BASE, handleResponse, type KnowledgeDocument } from '../../../api/client'

export type KnowledgePathResponse = {
  configured_path: string
  resolved_path: string
  is_custom: boolean
  is_accessible: boolean
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
    fetch(`${API_BASE}/api/knowledge/documents`).then((r) =>
      handleResponse<{ documents: KnowledgeDocument[] }>(r),
    ),

  uploadDocument: async (file: File, tags: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('tags', tags)
    return fetch(`${API_BASE}/api/knowledge/documents`, { method: 'POST', body: form }).then((r) =>
      handleResponse<{ document: KnowledgeDocument }>(r),
    )
  },

  uploadDocumentsBatch: async (files: File[], tags: string) => {
    const form = new FormData()
    for (const file of files) {
      form.append('files', file)
    }
    form.append('tags', tags)
    return fetch(`${API_BASE}/api/knowledge/documents/batch`, { method: 'POST', body: form }).then((r) =>
      handleResponse<{ documents: KnowledgeDocument[]; errors: string[] }>(r),
    )
  },

  deleteDocument: (id: string) =>
    fetch(`${API_BASE}/api/knowledge/documents/${id}`, { method: 'DELETE' }).then((r) =>
      handleResponse<{ ok: boolean }>(r),
    ),

  retrieve: (query: string, sources: string[]) =>
    fetch(`${API_BASE}/api/knowledge/retrieve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, sources }),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getKnowledgePath: () =>
    fetch(`${API_BASE}/api/knowledge/path`).then((r) =>
      handleResponse<KnowledgePathResponse>(r),
    ),

  setKnowledgePath: (path: string) =>
    fetch(`${API_BASE}/api/knowledge/path`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }).then((r) => handleResponse<KnowledgePathResponse>(r)),

  checkIntegrity: () =>
    fetch(`${API_BASE}/api/knowledge/admin/integrity`).then((r) =>
      handleResponse<KnowledgeIntegrityResponse>(r),
    ),

  rebuildIndex: () =>
    fetch(`${API_BASE}/api/knowledge/admin/rebuild-index`, {
      method: 'POST',
    }).then((r) => handleResponse<KnowledgeRebuildResponse>(r)),

  exportJsonBackup: () =>
    fetch(`${API_BASE}/api/knowledge/admin/export-json`, {
      method: 'POST',
    }).then((r) => handleResponse<KnowledgeExportResponse>(r)),
}
