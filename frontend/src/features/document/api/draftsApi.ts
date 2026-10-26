import { API_BASE, getAuthHeaders, handleResponse } from '../../../api/client'
import type { ChatPersistMessage, DocumentArtifact } from '../hooks/useChatPersistence'

export interface SaveDraftPayload {
  id: string
  name?: string
  title?: string
  specification?: string
  feature_slug?: string
  lastInteraction?: string
  messages?: ChatPersistMessage[]
  documentContent?: string
  artifacts?: DocumentArtifact[]
}

export interface DraftItem {
  id: string
  title: string
  specification: string
  last_interaction: string
  folder_path: string
  message_count: number
  artifact_count: number
  artifacts: Array<{
    id: string
    title: string
    extension: string
    path: string
    md_path?: string
  }>
  updated_at: string
}

export const draftsApi = {
  saveDraft: async (payload: SaveDraftPayload) => {
    const res = await fetch(`${API_BASE}/api/drafts/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    })
    return handleResponse<{ ok: boolean; draft: DraftItem; message: string }>(res)
  },

  listDrafts: async (specification?: string) => {
    const query = specification ? `?specification=${encodeURIComponent(specification)}` : ''
    const res = await fetch(`${API_BASE}/api/drafts/list${query}`, {
      headers: { ...getAuthHeaders() },
    })
    return handleResponse<{ ok: boolean; drafts: DraftItem[] }>(res)
  },

  getDraft: async (draftId: string) => {
    const res = await fetch(`${API_BASE}/api/drafts/${draftId}`, {
      headers: { ...getAuthHeaders() },
    })
    return handleResponse<{ ok: boolean; draft: DraftItem }>(res)
  },

  deleteDraft: async (draftId: string) => {
    const res = await fetch(`${API_BASE}/api/drafts/${draftId}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    })
    return handleResponse<{ ok: boolean; message: string }>(res)
  },
}
