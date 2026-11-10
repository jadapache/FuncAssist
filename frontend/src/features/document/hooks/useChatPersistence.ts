import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
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
  const [searchParams, setSearchParams] = useSearchParams()
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>()
  const urlSessionId = routeSessionId || searchParams.get('session')
  const initialUrlSessionId = useRef(urlSessionId)
  const hasLocalConversationRef = useRef(false)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(urlSessionId || null)

  const syncUrlSession = useCallback(
    (sessionId: string | null) => {
      if (routeSessionId) return
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (sessionId) {
            next.set('session', sessionId)
          } else {
            next.delete('session')
          }
          return next
        },
        { replace: true },
      )
    },
    [routeSessionId, setSearchParams],
  )

  // Load sessions and messages directly from the remote PostgreSQL entity.
  useEffect(() => {
    let isCancelled = false
    chatSessionsApi
      .getSessions(featureSlug)
      .then((remoteSessions) => {
        if (isCancelled) return
        setConversations((current) => {
          const remoteIds = new Set(remoteSessions.map((conversation) => conversation.id))
          const localOnly = current.filter((conversation) => !remoteIds.has(conversation.id))
          // Deduplicate messages within remoteSessions to ensure no duplicates are loaded
          const cleanedRemote = remoteSessions.map((sess) => {
            const seen = new Set<string>()
            const dedupedMessages = sess.messages.filter((m) => {
              const key = m.id ? m.id : `${m.role}-${m.content.trim()}`
              if (seen.has(key)) return false
              seen.add(key)
              return true
            })
            return { ...sess, messages: dedupedMessages }
          })
          return [...localOnly, ...cleanedRemote]
        })
        const matched = initialUrlSessionId.current
          ? remoteSessions.find((c) => c.id === initialUrlSessionId.current)
          : null
        const initialId = matched?.id || remoteSessions[0]?.id || null
        if (!hasLocalConversationRef.current) {
          setActiveConversationId(initialId)
        }
        if (initialId && !initialUrlSessionId.current && !hasLocalConversationRef.current) {
          syncUrlSession(initialId)
        }
      })
      .catch((err) => {
        console.debug('[useChatPersistence] Failed to fetch remote sessions:', err)
      })

    return () => {
      isCancelled = true
    }
  }, [featureSlug, userId, syncUrlSession])

  // Sync state if user changes query param externally or navigates history
  useEffect(() => {
    if (urlSessionId && urlSessionId !== activeConversationId) {
      if (conversations.some((c) => c.id === urlSessionId)) {
        setActiveConversationId(urlSessionId)
      }
    }
  }, [urlSessionId, conversations, activeConversationId])

  // Track last synced state snapshot to avoid redundant backend roundtrips
  const lastSyncedHashRef = useRef<Record<string, string>>({})

  // Sync changes to the persisted chat entity whenever conversations change.
  useEffect(() => {
    const nonEmpties = conversations.filter(
      (c) => c.messages.length > 0 || (c.artifacts && c.artifacts.length > 0),
    )
    // Debounced background sync to backend
    const timer = setTimeout(() => {
      nonEmpties.forEach((conv) => {
        const hash = `${conv.messages.length}-${(conv.artifacts || []).length}-${(conv.documentContent || '').length}`
        if (lastSyncedHashRef.current[conv.id] === hash) {
          return
        }
        lastSyncedHashRef.current[conv.id] = hash
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
      hasLocalConversationRef.current = true
      setActiveConversationId(newConv.id)
      syncUrlSession(newConv.id)
      return newConv
    },
    [conversations.length, syncUrlSession],
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
    [activeConversationId, syncUrlSession],
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
          const nextId = filtered.length > 0 ? filtered[0].id : null
          setActiveConversationId(nextId)
          syncUrlSession(nextId)
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
  const switchConversation = useCallback(
    (id: string) => {
      setActiveConversationId(id)
      syncUrlSession(id)
    },
    [syncUrlSession],
  )

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
