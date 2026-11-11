// Pages
export { ChatPage } from './pages/ChatPage'
export { default } from './pages/ChatPage'

// Workspace & Chat UI Components
export { ChatWorkspace, CHAT_SOURCE_OPTIONS, DEFAULT_CHAT_CONFIG } from './components/ChatWorkspace'
export { ChatHistorySidebar } from './components/ChatHistorySidebar'
export { AgenticThinkingBubble } from './components/AgenticThinkingBubble'

// Chat Hooks
export { useChatPersistence } from './hooks/useChatPersistence'
export { useAgenticGeneration } from './hooks/useAgenticGeneration'
export { useAgentRun } from './hooks/useAgentRun'
export { useArtifacts } from './hooks/useArtifacts'

// Chat API & Types
export * from './api/chatSessionsApi'
export * from './api/docAgentApi'
export * from './types/agentEvents'
