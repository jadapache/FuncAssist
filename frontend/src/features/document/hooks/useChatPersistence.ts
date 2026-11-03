import { useCallback, useEffect, useState } from 'react'
import type { Artifact } from '../../../types/artifacts'
import { draftsApi } from '../../../features/document/api/draftsApi'
import { chatSessionsApi } from '../../../features/document/api/chatSessionsApi'

export type DocumentArtifact = Artifact


export interface ChatConversation {
  id: string
  name: string
  lastInteraction: string // ISO string
  messages: ChatPersistMessage[]
  documentContent: string
  artifacts?: DocumentArtifact[]
  activeArtifactId?: string
}

export interface ChatAttachment {
  id: string
  name: string
  type: 'image' | 'file'
  dataUrl?: string
  size?: number
  content?: string
}

export interface ChatPersistMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  /** Collapsed thinking trace steps attached to assistant messages */
  thinkingSteps?: ThinkingStep[]
  attachments?: ChatAttachment[]
}

export interface ThinkingStep {
  id: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  details?: string
}

/**
 * Hook for persisting and managing chat conversation history in PostgreSQL / Borradores.
 */
export function useChatPersistence(featureSlug: string, userId?: string | null) {
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)

  // Load sessions and messages directly from the remote PostgreSQL entity.
  useEffect(() => {
    let isCancelled = false
    chatSessionsApi.getSessions(featureSlug).then((remoteSessions) => {
      if (isCancelled) return
      setConversations(remoteSessions)
      setActiveConversationId((prev) => prev && remoteSessions.some((c) => c.id === prev) ? prev : remoteSessions[0]?.id ?? null)
    }).catch((err) => {
      console.debug('[useChatPersistence] Failed to fetch remote sessions:', err)
    })

    return () => {
      isCancelled = true
    }
  }, [featureSlug, userId])

  // Sync changes to the persisted chat entity whenever conversations change.
  useEffect(() => {
    const nonEmpties = conversations.filter(
      (c) => c.messages.length > 0 || (c.artifacts && c.artifacts.length > 0),
    )
    // Debounced background sync to backend
    const timer = setTimeout(() => {
      nonEmpties.forEach((conv) => {
        draftsApi
          .saveDraft({
            id: conv.id,
            name: conv.name,
            title: conv.name,
            feature_slug: featureSlug,
            specification: featureSlug,
            lastInteraction: conv.lastInteraction,
            messages: conv.messages,
            documentContent: conv.documentContent,
            artifacts: conv.artifacts,
          })
          .catch((err) => {
            console.debug('[useChatPersistence] Draft background sync failed:', err)
          })
      })
    }, 600)

    return () => clearTimeout(timer)
  }, [conversations, featureSlug, userId])

  const activeConversation = conversations.find((c) => c.id === activeConversationId) ?? null

  /**
   * Create a brand new conversation and set it as active.
   */
  const createConversation = useCallback(
    (name?: string): ChatConversation => {
      const newConv: ChatConversation = {
        id: crypto.randomUUID(),
        name: name || `Conversación ${conversations.length + 1}`,
        lastInteraction: new Date().toISOString(),
        messages: [],
        documentContent: '',
        artifacts: [],
        activeArtifactId: undefined,
      }
      setConversations((prev) => [newConv, ...prev])
      setActiveConversationId(newConv.id)
      return newConv
    },
    [conversations.length],
  )

  /**
   * Update the active (or explicitly specified) conversation's messages and/or document content.
   */
  const updateConversation = useCallback(
    (
      updates: Partial<Pick<ChatConversation, 'messages' | 'documentContent' | 'name' | 'artifacts' | 'activeArtifactId'>>,
      targetId?: string,
    ) => {
      const idToUpdate = targetId ?? activeConversationId
      if (!idToUpdate) return
      setConversations((prev) =>
        prev.map((c) =>
          c.id === idToUpdate
            ? {
                ...c,
                ...updates,
                lastInteraction: new Date().toISOString(),
              }
            : c,
        ),
      )
    },
    [activeConversationId],
  )

  /**
   * Rename a conversation.
   */
  const renameConversation = useCallback((id: string, newName: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, name: newName } : c)),
    )
  }, [])

  /**
   * Delete a conversation.
   */
  const deleteConversation = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const filtered = prev.filter((c) => c.id !== id)
        if (activeConversationId === id) {
          setActiveConversationId(filtered.length > 0 ? filtered[0].id : null)
        }
        return filtered
      })
      draftsApi.deleteDraft(id).catch((err) => {
        console.debug('[useChatPersistence] Delete draft error:', err)
      })
      chatSessionsApi.deleteSession(id).catch((err) => {
        console.debug('[useChatPersistence] Delete chat session error:', err)
      })
    },
    [activeConversationId],
  )

  /**
   * Switch to an existing conversation.
   */
  const switchConversation = useCallback((id: string) => {
    setActiveConversationId(id)
  }, [])

  return {
    conversations,
    activeConversation,
    activeConversationId,
    createConversation,
    updateConversation,
    renameConversation,
    deleteConversation,
    switchConversation,
  }
}
