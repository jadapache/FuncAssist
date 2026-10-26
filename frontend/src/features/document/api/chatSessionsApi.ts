import { API_BASE, getAuthHeaders, handleResponse } from '../../../api/client'
import type { ChatConversation, DocumentArtifact } from '../hooks/useChatPersistence'

export interface BackendSessionPayload {
  id: string
  title?: string
  feature_slug?: string
  document_content?: string
  artifacts?: DocumentArtifact[]
  active_artifact_id?: string
  created_at: string
  updated_at: string
}

export const chatSessionsApi = {
  getSessions: async (featureSlug?: string): Promise<ChatConversation[]> => {
    const qs = featureSlug ? `?feature_slug=${encodeURIComponent(featureSlug)}` : ''
    const res = await fetch(`${API_BASE}/api/chat/sessions${qs}`, {
      headers: { ...getAuthHeaders() },
    })
    const data = await handleResponse<{ sessions: BackendSessionPayload[] }>(res)

    return (data.sessions || []).map((s) => ({
      id: s.id,
      name: s.title || 'Conversación',
      lastInteraction: s.updated_at || s.created_at || new Date().toISOString(),
      messages: [],
      documentContent: s.document_content || '',
      artifacts: s.artifacts || [],
      activeArtifactId: s.active_artifact_id,
    }))
  },

  deleteSession: async (sessionId: string): Promise<boolean> => {
    const res = await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    })
    const data = await handleResponse<{ ok: boolean }>(res)
    return data.ok
  },
}
