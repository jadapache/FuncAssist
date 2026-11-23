/**
 * Chat persistence domain types (framework-agnostic).
 * Ported from the React `useChatPersistence` hook so that API modules, storage
 * utilities and Angular stores can share them without depending on any UI layer.
 */
import type { Artifact } from '../../../types/artifacts'

export type DocumentArtifact = Artifact

export interface ChatConversation {
  id: string
  name: string
  lastInteraction: string
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
  thinkingSteps?: ThinkingStep[]
  attachments?: ChatAttachment[]
}

export interface ThinkingStep {
  id: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  details?: string
}

export type ChatConversationUpdate = Partial<
  Pick<ChatConversation, 'messages' | 'documentContent' | 'name' | 'artifacts' | 'activeArtifactId' | 'lastInteraction'>
>
