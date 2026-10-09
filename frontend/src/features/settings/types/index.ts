import type { Cpu } from 'lucide-react'

export type TabType = 'ai_models' | 'templates' | 'integrations' | 'knowledge'

export type BuiltInModel = {
  id: string
  name: string
  tag: string
  description: string
  size: string
  tokens: string
}

export type RecommendedModel = {
  id: string
  name: string
}

export type CloudProvider = {
  id: string
  name: string
  recommendedModels?: RecommendedModel[]
}

export type SettingsTabItem = {
  id: TabType
  label: string
  subtitle: string
  icon: typeof Cpu
  badgeCount?: number
}

export type AISettings = {
  provider: string | null
  model: string | null
  transcription_provider?: string | null
  transcription_model?: string | null
  voice_command_provider?: string | null
  voice_command_model?: string | null
  openai_api_key_set: boolean
  claude_api_key_set: boolean
  groq_api_key_set: boolean
  gemini_api_key_set?: boolean
  transcription_groq_api_key_set?: boolean
  transcription_openai_api_key_set?: boolean
  ollama_base_url: string
  active_api_key_set?: boolean
}

export type ModelCatalogItem = {
  id: string
  raw_id: string
  name: string
  provider: 'groq' | 'openai' | 'claude' | 'gemini' | 'ollama' | 'builtin' | 'local' | string
  provider_name: string
  description: string
  context_window: string
  context_length: number
  task_type: 'chat_writing' | 'transcription'
  task_label: string
  tier_type: 'free' | 'paid' | 'freemium'
  pricing_prompt: number
  pricing_completion: number
  pricing_label: string
  rate_limits: string
  max_output_tokens?: number
  badge?: string
  is_free: boolean
  size?: string
  accuracy?: string
  is_downloaded?: boolean
  disk_size_mb?: number
}

export type LocalWhisperModelInfo = {
  id: string
  name: string
  size: string
  accuracy: string
  description: string
  is_downloaded: boolean
  disk_size_mb: number
  file_path?: string | null
}

export type LocalBuiltinModelInfo = {
  id: string
  name: string
  size: string
  tokens?: string
  description: string
  filename?: string
  is_downloaded: boolean
  disk_size_mb: number
  file_path?: string | null
}

export type ModelCatalogResponse = {
  updated_at: string
  source: string
  providers: string[]
  models: ModelCatalogItem[]
  error?: string
}

export type CorporateTemplate = {
  id: string
  title: string
  filename: string
  file_type: string
  file_size: number
  module: string
  tags?: string[]
  created_at: string
}

export type SystemTag = {
  tag: string
  label: string
  description: string
  type?: 'ai' | 'function'
}

export type TemplateDetail = {
  template: CorporateTemplate
  content: string
  header_content?: string
  footer_content?: string
  detected_tags: string[]
  system_tags: SystemTag[]
}

export type AIPromptTemplate = {
  version: number
  feature: string
  allowed_sources?: string[]
  system?: string
  user_template?: string
  [key: string]: unknown
}

export type AIRubric = {
  version: number
  feature: string
  criteria: string[]
  [key: string]: unknown
}
