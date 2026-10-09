import { knowledgeApi } from '../features/knowledge/api/knowledgeApi'
import { aiSettingsApi } from '../features/settings/api/aiSettingsApi'
import { featuresApi } from './modules/features'
import { docAgentApi } from '../features/document/api/docAgentApi'
import { integrationsApi } from '../features/integrations/api/integrationsApi'
import { templatesApi } from '../features/settings/api/templatesApi'
import { settingsApi } from '../features/settings/api/settingsApi'
import { userApi } from './modules/user'
import type { UserProfile, UserRole } from './modules/user'
import { transcriptionApi } from '../features/transcription/api/transcriptionApi'
import { draftsApi } from '../features/document/api/draftsApi'

export type {
  KnowledgePathResponse,
  KnowledgeIntegrityResponse,
  KnowledgeRebuildResponse,
  KnowledgeExportResponse,
} from '../features/knowledge/api/knowledgeApi'
export type { AppSettings, IntegrationInfo, TestConnectionResult } from '../types'
export type {
  MediaMetadata,
  TranscriptionSegment,
  TranscriptionSummary,
  TranscriptionProgress,
  TranscriptionResult,
  TranscribeOptions,
} from '../features/transcription/api/transcriptionApi'
export type { UserProfile, UserRole }

export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export const handleResponse = async <T,>(response: Response): Promise<T> => {
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // ignore
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export type KnowledgeDocument = {
  id: string
  filename: string
  tags: string[]
  chunk_count: number
  uploaded_at: string
  char_count: number
}

export type LLMArtifact = {
  index: number
  title: string
  extension: string
  content: string
}

export type GroundedResult = {
  ok: boolean
  refused: boolean
  reason?: string | null
  answer?: string | null
  answer_clean?: string | null
  artifacts?: LLMArtifact[]
  citations: Array<{
    index: number
    id: string
    source_type: string
    source_label: string
    title: string
  }>
  context?: {
    query: string
    chunks: Array<Record<string, unknown>>
    missing_sources: string[]
    used_sources: string[]
  }
  meta?: {
    prompt_version?: string
    rubric_version?: string
    provider?: string
    model?: string
    log_id?: string
    artifact_count?: number
    [key: string]: unknown
  }
}

export type AgenticPromptResponse = {
  answer?: string
  answer_clean?: string
  artifacts?: LLMArtifact[]
  assistant_message?: string
  operations?: Record<string, unknown>[]
  planned_operations?: Record<string, unknown>[]
  document_updates?: string
  intent_detected?: string
  requires_document_mutation?: boolean
  rag_knowledge_used?: string[]
  validation_status?: { valid: boolean; details: string[] }
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

export type FeaturePayload = {
  query: string
  document_ids: string[]
  chat_context?: string
  sources?: string[]
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

export const api = {
  ...userApi,
  ...knowledgeApi,
  ...aiSettingsApi,
  ...featuresApi,
  ...docAgentApi,
  ...integrationsApi,
  ...templatesApi,
  ...settingsApi,
  ...transcriptionApi,
  ...draftsApi,
}

export const apiClient = api
