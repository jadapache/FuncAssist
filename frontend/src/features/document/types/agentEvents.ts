export type AgentEventType =
  | 'run.started'
  | 'run.status'
  | 'run.step.started'
  | 'run.step.completed'
  | 'run.step.failed'
  | 'message.delta'
  | 'source.found'
  | 'artifact.created'
  | 'artifact.updated'
  | 'interaction.required'
  | 'run.heartbeat'
  | 'run.completed'
  | 'run.failed'
  | 'run.cancelled'

export type StepState = 'pending' | 'in_progress' | 'completed' | 'failed'

export interface AgentRunStep {
  stepId: string
  label: string
  status: StepState
  details?: string
}

export interface AgentRunSource {
  sourceId: string
  title: string
  sourceType: string
  snippet?: string
  score?: number
}

export interface AgentRunArtifact {
  artifactId: string
  title: string
  extension: string
  content: string
  versionId?: string
}

export interface AgentEventEnvelope {
  version?: number
  run_id?: string
  conversation_id?: string
  sequence?: number
  type: AgentEventType | 'token' | 'intent' | 'full' | 'error' | 'done'
  timestamp?: string
  data?: unknown
  text?: string
  intent?: string
  message?: string
}

export interface AgentRunState {
  runId: string | null
  conversationId: string | null
  status: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled'
  activeStatusText: string
  steps: AgentRunStep[]
  sources: AgentRunSource[]
  artifacts: AgentRunArtifact[]
  liveMessage: string
  errorMessage: string | null
}

