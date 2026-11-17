import React, { createContext, useContext, useMemo, useState } from 'react'
import { useAuth } from './AuthContext'
import { useChatPersistence, type ChatConversation } from '../features/chat/hooks/useChatPersistence'

interface ChatContextValue {
  conversations: ChatConversation[]
  activeConversation: ChatConversation | null
  activeConversationId: string | null
  createConversation: (name?: string) => ChatConversation
  updateConversation: (
    updates: Partial<
      Pick<
        ChatConversation,
        'messages' | 'documentContent' | 'name' | 'artifacts' | 'activeArtifactId' | 'lastInteraction'
      >
    >,
    targetId?: string,
  ) => void
  renameConversation: (id: string, name: string) => void
  deleteConversation: (id: string) => void
  switchConversation: (id: string) => void
  searchQuery: string
  setSearchQuery: (query: string) => void
}

const ChatContext = createContext<ChatContextValue | undefined>(undefined)

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth()
  const [searchQuery, setSearchQuery] = useState('')

  const persistence = useChatPersistence('chat', user?.id)

  const value = useMemo(
    () => ({
      ...persistence,
      searchQuery,
      setSearchQuery,
    }),
    [persistence, searchQuery],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export const useChat = (): ChatContextValue => {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
}
