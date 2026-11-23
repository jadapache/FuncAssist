export type { Artifact, ArtifactExtension } from '../../../types/artifacts'

export type LLMArtifact = {
  index: number
  title: string
  extension: string
  content: string
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
