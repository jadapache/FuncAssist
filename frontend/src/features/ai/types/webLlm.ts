export type ModelPreference = 'speed' | 'balanced' | 'quality'

export interface WebLLMModelDefinition {
  id: string
  name: string
  tag: string
  description: string
  downloadSize: string
  vramRequiredMB: number
  vramFormatted: string
  contextWindow: string
  tier: ModelPreference
  requiredFeatures?: string[]
  isDownloaded?: boolean
}

export interface HardwareProfile {
  hasWebGPU: boolean
  hasShaderF16: boolean
  adapterName: string
  deviceMemoryGB: number
  hardwareConcurrency: number
  maxBufferSizeMB: number
  tier: 'low' | 'medium' | 'high'
}

export interface ModelEvaluation {
  model: WebLLMModelDefinition
  isCompatible: boolean
  isRecommended: boolean
  reason: string
}

export interface WebLLMInitProgress {
  progress: number
  text: string
  timeElapsed: number
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface SummarizeRequest {
  text: string
  instructions?: string
  systemPrompt?: string
  maxTokens?: number
  temperature?: number
}

export interface SummarizeResult {
  summary: string
  modelUsed: string
  tokensGenerated?: number
}

export interface ArtifactGenerationRequest {
  instructions: string
  context?: string
  systemPrompt?: string
  maxTokens?: number
  temperature?: number
}

export interface ArtifactGenerationResult {
  content: string
  modelUsed: string
  tokensGenerated?: number
}
