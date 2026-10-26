import { useCallback, useRef, useState } from 'react'
import { docAgentApi, type AgenticPromptPayload } from '../api/docAgentApi'
import type {
  AgentEventEnvelope,
  AgentRunArtifact,
  AgentRunSource,
  AgentRunState,
  AgentRunStep,
} from '../types/agentEvents'
import type { AgenticPromptResponse } from '../../../api/client'

const INITIAL_RUN_STATE: AgentRunState = {
  runId: null,
  conversationId: null,
  status: 'idle',
  activeStatusText: '',
  steps: [],
  sources: [],
  artifacts: [],
  liveMessage: '',
  errorMessage: null,
}

export function useAgentRun() {
  const [runState, setRunState] = useState<AgentRunState>(INITIAL_RUN_STATE)
  const abortControllerRef = useRef<AbortController | null>(null)

  const resetRun = useCallback(() => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setRunState(INITIAL_RUN_STATE)
  }, [])

  const handleEvent = useCallback((event: AgentEventEnvelope) => {
    setRunState((prev) => processIncomingEvent(prev, event))
  }, [])

  const cancelRun = useCallback(async () => {
    const currentRunId = runState.runId
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setRunState((prev) => ({
      ...prev,
      status: 'cancelled',
      activeStatusText: 'Cancelado por el usuario',
    }))
    if (currentRunId) {
      try {
        await docAgentApi.cancelRun(currentRunId)
      } catch {
        // Run already terminated on server
      }
    }
  }, [runState.runId])

  const executeRun = useCallback(
    async (
      payload: AgenticPromptPayload,
      onChunk: (accumulated: string, delta: string) => void,
      onIntent?: (intent: string) => void,
    ): Promise<AgenticPromptResponse> => {
      const controller = new AbortController()
      abortControllerRef.current = controller

      const generatedRunId = payload.run_id || `run-${crypto.randomUUID().slice(0, 8)}`
      setRunState({
        ...INITIAL_RUN_STATE,
        runId: generatedRunId,
        status: 'running',
        activeStatusText: 'Iniciando agente...',
      })

      try {
        return await docAgentApi.agenticPromptStream(
          { ...payload, run_id: generatedRunId },
          onChunk,
          onIntent,
          handleEvent,
          controller.signal,
        )
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Error en la ejecución'
        setRunState((prev) => ({
          ...prev,
          status: prev.status === 'cancelled' ? 'cancelled' : 'failed',
          errorMessage: message,
        }))
        throw err
      } finally {
        abortControllerRef.current = null
      }
    },
    [handleEvent],
  )

  return {
    runState,
    executeRun,
    cancelRun,
    resetRun,
  }
}

function processIncomingEvent(prev: AgentRunState, ev: AgentEventEnvelope): AgentRunState {
  if (ev.type === 'run.started') {
    return handleRunStarted(prev, ev)
  }
  if (ev.type === 'run.step.started') {
    return handleStepStarted(prev, ev)
  }
  if (ev.type === 'run.step.completed' || ev.type === 'run.step.failed') {
    return handleStepFinished(prev, ev)
  }
  if (ev.type === 'source.found') {
    return handleSourceFound(prev, ev)
  }
  if (ev.type === 'artifact.created' || ev.type === 'artifact.updated') {
    return handleArtifactEvent(prev, ev)
  }
  if (ev.type === 'run.completed') {
    return { ...prev, status: 'completed', activeStatusText: 'Listo' }
  }
  if (ev.type === 'run.cancelled') {
    return { ...prev, status: 'cancelled', activeStatusText: 'Cancelado' }
  }
  return prev
}

function handleRunStarted(prev: AgentRunState, ev: AgentEventEnvelope): AgentRunState {
  const dataObj = typeof ev.data === 'object' && ev.data !== null ? (ev.data as Record<string, unknown>) : null
  const profile = dataObj?.task_profile ? String(dataObj.task_profile) : 'general'
  return {
    ...prev,
    runId: ev.run_id || prev.runId,
    conversationId: ev.conversation_id || prev.conversationId,
    status: 'running',
    activeStatusText: `Analizando requerimiento (${profile})...`,
  }
}

function handleStepStarted(prev: AgentRunState, ev: AgentEventEnvelope): AgentRunState {
  const dataObj = typeof ev.data === 'object' && ev.data !== null ? (ev.data as Record<string, unknown>) : null
  const stepId = dataObj?.step_id ? String(dataObj.step_id) : `step-${prev.steps.length + 1}`
  const label = dataObj?.label ? String(dataObj.label) : 'Procesando etapa...'
  const newStep: AgentRunStep = {
    stepId,
    label,
    status: 'in_progress',
    details: dataObj?.details ? String(dataObj.details) : undefined,
  }
  const existingIndex = prev.steps.findIndex((s) => s.stepId === stepId)
  const steps = existingIndex >= 0 ? prev.steps.map((s, i) => (i === existingIndex ? newStep : s)) : [...prev.steps, newStep]
  return { ...prev, steps, activeStatusText: label }
}

function handleStepFinished(prev: AgentRunState, ev: AgentEventEnvelope): AgentRunState {
  const dataObj = typeof ev.data === 'object' && ev.data !== null ? (ev.data as Record<string, unknown>) : null
  const stepId = dataObj?.step_id ? String(dataObj.step_id) : ''
  const isFailed = ev.type === 'run.step.failed'
  const steps = prev.steps.map((s) => (s.stepId === stepId ? { ...s, status: isFailed ? ('failed' as const) : ('completed' as const) } : s))
  return { ...prev, steps }
}

function handleSourceFound(prev: AgentRunState, ev: AgentEventEnvelope): AgentRunState {
  const dataObj = typeof ev.data === 'object' && ev.data !== null ? (ev.data as Record<string, unknown>) : null
  if (!dataObj) return prev
  const newSource: AgentRunSource = {
    sourceId: String(dataObj.source_id || `src-${prev.sources.length + 1}`),
    title: String(dataObj.title || 'Fuente RAG'),
    sourceType: String(dataObj.source_type || 'document'),
    snippet: dataObj.snippet ? String(dataObj.snippet) : undefined,
    score: typeof dataObj.score === 'number' ? dataObj.score : undefined,
  }
  return { ...prev, sources: [...prev.sources, newSource] }
}

function handleArtifactEvent(prev: AgentRunState, ev: AgentEventEnvelope): AgentRunState {
  const dataObj = typeof ev.data === 'object' && ev.data !== null ? (ev.data as Record<string, unknown>) : null
  if (!dataObj) return prev
  const artifactId = String(dataObj.artifact_id || `art-${prev.artifacts.length + 1}`)
  const newArt: AgentRunArtifact = {
    artifactId,
    title: String(dataObj.title || 'Documento'),
    extension: String(dataObj.extension || 'docx'),
    content: String(dataObj.content || ''),
    versionId: dataObj.version_id ? String(dataObj.version_id) : undefined,
  }
  const existingIdx = prev.artifacts.findIndex((a) => a.artifactId === artifactId)
  const artifacts = existingIdx >= 0 ? prev.artifacts.map((a, i) => (i === existingIdx ? newArt : a)) : [...prev.artifacts, newArt]
  return { ...prev, artifacts }
}
