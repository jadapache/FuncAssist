import { useCallback, useEffect, useState } from 'react'
import type { Artifact } from '../types/artifacts'
import { loadChatConversations, saveChatConversations } from '../utils/chatStorage'
import { draftsApi } from '../api/modules/drafts'

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

export interface ChatPersistMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  /** Collapsed thinking trace steps attached to assistant messages */
  thinkingSteps?: ThinkingStep[]
}

export interface ThinkingStep {
  id: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  details?: string
}

/**
 * Hook for persisting and managing chat conversation history in localStorage and Documents/QA MGMT/Borradores.
 */
export function useChatPersistence(featureSlug: string) {
  const [conversations, setConversations] = useState<ChatConversation[]>(() =>
    loadChatConversations(featureSlug),
  )
  const [activeConversationId, setActiveConversationId] = useState<string | null>(() => {
    const loaded = loadChatConversations(featureSlug)
    return loaded.length > 0 ? loaded[0].id : null
  })

  // Persist to localStorage and sync to backend Borradores whenever conversations change (only non-empty conversations)
  useEffect(() => {
    const nonEmpties = conversations.filter(
      (c) => c.messages.length > 0 || (c.artifacts && c.artifacts.length > 0),
    )
    saveChatConversations(featureSlug, nonEmpties)

    // Debounced background sync to backend Documents/QA MGMT/Borradores
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
  }, [conversations, featureSlug])


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
   * Update the active conversation's messages and/or document content.
   */
  const updateConversation = useCallback(
    (updates: Partial<Pick<ChatConversation, 'messages' | 'documentContent' | 'name' | 'artifacts' | 'activeArtifactId'>>) => {
      if (!activeConversationId) return
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeConversationId
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
