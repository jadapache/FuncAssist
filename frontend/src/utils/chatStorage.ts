/**
 * Capa de acceso a localStorage para persistencia de conversaciones de chat.
 */

import type { ChatConversation } from '../features/document/hooks/useChatPersistence'

const STORAGE_PREFIX = 'funcassist_chats_'

export function getChatStorageKey(featureSlug: string, userId?: string | null): string {
  const prefix = userId ? `${STORAGE_PREFIX}${userId}_` : STORAGE_PREFIX
  return `${prefix}${featureSlug}`
}

export function loadChatConversations(featureSlug: string, userId?: string | null): ChatConversation[] {
  try {
    const raw = localStorage.getItem(getChatStorageKey(featureSlug, userId))
    if (!raw) return []
    return JSON.parse(raw) as ChatConversation[]
  } catch {
    return []
  }
}

export function saveChatConversations(
  featureSlug: string,
  conversations: ChatConversation[],
  userId?: string | null,
): void {
  try {
    localStorage.setItem(getChatStorageKey(featureSlug, userId), JSON.stringify(conversations))
  } catch {
    console.warn('[chatStorage] Failed to persist chat history to localStorage')
  }
}
