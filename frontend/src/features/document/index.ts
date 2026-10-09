// Core workspace components
export { AgenticDocumentWorkspace } from './components/AgenticDocumentWorkspace'
export { FeatureWorkspace } from './components/FeatureWorkspace'
export { ArtifactsStudio } from './components/ArtifactsStudio'
export { DocumentPanel } from './components/DocumentPanel'
export { ChatHistorySidebar } from './components/ChatHistorySidebar'
export { AgenticThinkingBubble } from './components/AgenticThinkingBubble'

// Hooks
export { useAgenticGeneration } from './hooks/useAgenticGeneration'
export { useArtifacts } from './hooks/useArtifacts'
export { useChatPersistence } from './hooks/useChatPersistence'
export { useDocumentHistory } from './hooks/useDocumentHistory'

// APIs
export * from './api/docAgentApi'
export * from './api/draftsApi'
