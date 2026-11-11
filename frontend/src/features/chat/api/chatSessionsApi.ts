import { API_BASE, getAuthHeaders, handleResponse } from '../../../api/client'
import type { ChatConversation, DocumentArtifact } from '../hooks/useChatPersistence'

export interface BackendSessionPayload {
  id: string
  title?: string
  feature_slug?: string
  document_content?: string
  documentContent?: string
  artifacts?: DocumentArtifact[]
  active_artifact_id?: string
  activeArtifactId?: string
  created_at: string
  updated_at: string
}

interface BackendMessagePayload {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: string
  created_at?: string
  attachments?: ChatConversation['messages'][number]['attachments']
}

export const chatSessionsApi = {
  getSessions: async (featureSlug?: string): Promise<ChatConversation[]> => {
    const qs = featureSlug ? `?feature_slug=${encodeURIComponent(featureSlug)}` : ''
    const res = await fetch(`${API_BASE}/api/chat/sessions${qs}`, {
      headers: { ...getAuthHeaders() },
    })
    const data = await handleResponse<{ sessions: BackendSessionPayload[] }>(res)

    const sessions = await Promise.all((data.sessions || []).map(async (s) => {
      const detailRes = await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(s.id)}`, {
        headers: { ...getAuthHeaders() },
      })
      const detail = await handleResponse<{ session?: BackendSessionPayload & { messages?: BackendMessagePayload[] } }>(detailRes)
      const messages = (detail.session?.messages || [])
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .map((message) => ({
          id: message.id,
          role: message.role as 'user' | 'assistant',
          content: message.content,
          timestamp: message.created_at || message.timestamp || new Date().toISOString(),
          attachments: message.attachments,
        }))

      return {
        id: s.id,
        name: s.title || 'Conversación',
        lastInteraction: s.updated_at || s.created_at || new Date().toISOString(),
        messages,
        documentContent: s.document_content || s.documentContent || '',
        artifacts: s.artifacts || [],
        activeArtifactId: s.active_artifact_id || s.activeArtifactId,
      }
    }))
    sessions.sort((a, b) => new Date(b.lastInteraction).getTime() - new Date(a.lastInteraction).getTime())
    return sessions
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
