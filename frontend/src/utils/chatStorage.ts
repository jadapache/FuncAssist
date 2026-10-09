/**
 * Capa de acceso a localStorage para persistencia de conversaciones de chat.
 */

import type { ChatConversation } from '../features/document/hooks/useChatPersistence'

const STORAGE_PREFIX = 'qa_mgmt_chats_'

export function getChatStorageKey(featureSlug: string): string {
  return `${STORAGE_PREFIX}${featureSlug}`
}

export function loadChatConversations(featureSlug: string): ChatConversation[] {
  try {
    const raw = localStorage.getItem(getChatStorageKey(featureSlug))
    if (!raw) return []
    return JSON.parse(raw) as ChatConversation[]
  } catch {
    return []
  }
}

export function saveChatConversations(
  featureSlug: string,
  conversations: ChatConversation[],
): void {
  try {
    localStorage.setItem(getChatStorageKey(featureSlug), JSON.stringify(conversations))
  } catch {
    console.warn('[chatStorage] Failed to persist chat history to localStorage')
  }
}
