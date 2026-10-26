import {
  API_BASE,
  handleResponse,
  type AgenticPromptResponse,
} from '../../../api/client'
import type { AgentEventEnvelope } from '../types/agentEvents'

export interface EphemeralAttachmentDoc {
  id: string
  filename: string
  content: string
  char_count?: number
}

export interface AgenticPromptPayload {
  query: string
  feature?: string
  mode?: string
  images?: Array<{ name: string, data: string, mime_type?: string }>
  attached_docs?: Array<{ filename: string, content: string }>
  current_document?: string
  chat_context?: string[]
  sources?: string[]
  document_ids?: string[]
  template_id?: string
  run_id?: string
  conversation_id?: string
}


export const docAgentApi = {
  parseAttachment: async (file: File): Promise<EphemeralAttachmentDoc> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/api/doc-agent/parse-attachment`, {
      method: 'POST',
      body: form,
    })
    const data = await handleResponse<{ filename: string; content: string; char_count: number }>(res)
    return {
      id: crypto.randomUUID(),
      filename: data.filename,
      content: data.content,
      char_count: data.char_count,
    }
  },

  agenticPrompt: (payload: AgenticPromptPayload): Promise<AgenticPromptResponse> =>
    fetch(`${API_BASE}/api/doc-agent/agentic-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: payload.query,
        query: payload.query,
        feature: payload.feature,
        mode: payload.mode,
        images: payload.images,
        attachedDocs: payload.attached_docs,
        current_document: payload.current_document,
        chat_context: payload.chat_context,
        sources: payload.sources,
        document_ids: payload.document_ids,
        templateId: payload.template_id,
      }),
    }).then((r) =>
      handleResponse<AgenticPromptResponse>(r).then((res) => ({
        answer: res.answer || res.assistant_message || 'Procesado correctamente.',
        answer_clean: res.answer_clean,
        artifacts: res.artifacts,
        assistant_message: res.assistant_message,
        operations: res.operations || res.planned_operations || [],
        planned_operations: res.planned_operations,
        document_updates: res.document_updates,
        intent_detected: res.intent_detected,
        requires_document_mutation: res.requires_document_mutation,
        rag_knowledge_used: res.rag_knowledge_used,
        validation_status: res.validation_status,
      })),
    ),

  cancelRun: async (runId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/api/doc-agent/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
    })
    if (!res.ok) {
      throw new Error(`Failed to cancel run ${runId}`)
    }
  },

  agenticPromptStream: async (
    payload: AgenticPromptPayload,
    onChunk: (accumulatedText: string, chunk: string) => void,
    onIntent?: (intent: string) => void,
    onEvent?: (event: AgentEventEnvelope) => void,
    signal?: AbortSignal,
  ): Promise<AgenticPromptResponse> => {
    const res = await fetch(`${API_BASE}/api/doc-agent/agentic-prompt-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        prompt: payload.query,
        query: payload.query,
        feature: payload.feature,
        mode: payload.mode,
        images: payload.images,
        attachedDocs: payload.attached_docs,
        current_document: payload.current_document,
        chat_context: payload.chat_context,
        sources: payload.sources,
        document_ids: payload.document_ids,
        templateId: payload.template_id,
        runId: payload.run_id,
        conversationId: payload.conversation_id,
      }),
    })

    if (!res.ok) {
      let detail = `Request failed (${res.status})`
      try {
        const body = await res.json()
        detail = body.detail ?? detail
      } catch { }
      throw new Error(detail)
    }

    if (!res.body) {
      throw new Error('ReadableStream not supported in this environment.')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    const state = { accumulatedText: '', fullResponseData: null as AgenticPromptResponse | null }
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const parsed = parseEventLine(line.trim())
        if (parsed) {
          handleParsedEvent(parsed, state, { onChunk, onIntent, onEvent })
        }
      }
    }

    const fullResponseData = state.fullResponseData


    if (fullResponseData) {
      return {
        answer: fullResponseData.answer || fullResponseData.assistant_message || 'Procesado correctamente.',
        answer_clean: fullResponseData.answer_clean,
        artifacts: fullResponseData.artifacts,
        assistant_message: fullResponseData.assistant_message,
        operations: fullResponseData.operations || fullResponseData.planned_operations || [],
        planned_operations: fullResponseData.planned_operations,
        document_updates: fullResponseData.document_updates,
        intent_detected: fullResponseData.intent_detected,
        requires_document_mutation: fullResponseData.requires_document_mutation,
        rag_knowledge_used: fullResponseData.rag_knowledge_used,
        validation_status: fullResponseData.validation_status,
      }
    }

    if (!state.accumulatedText.trim()) {
      throw new Error(
        'El modelo no devolvió ninguna respuesta o la conexión falló. Verifica tu API Key y la configuración del modelo.',
      )
    }

    return {
      answer: state.accumulatedText,
      document_updates: state.accumulatedText,
    }
  },


  exportMejorasDocx: async (markdown: string, title?: string): Promise<Blob> => {
    const res = await fetch(`${API_BASE}/api/doc-agent/export-docx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown, title: title || 'Documento de Mejora y Requerimientos Funcionales' }),
    })
    if (!res.ok) {
      let detail = `Error al exportar (.docx)`
      try {
        const body = await res.json()
        detail = body.detail ?? detail
      } catch { }
      throw new Error(detail)
    }
    return res.blob()
  },
}

function parseEventLine(trimmed: string): AgentEventEnvelope | null {
  if (!trimmed.startsWith('data: ')) return null
  try {
    return JSON.parse(trimmed.slice(6)) as AgentEventEnvelope
  } catch {
    return null
  }
}

function handleParsedEvent(
  parsed: AgentEventEnvelope,
  state: { accumulatedText: string; fullResponseData: AgenticPromptResponse | null },
  callbacks: {
    onChunk: (accumulatedText: string, chunk: string) => void
    onIntent?: (intent: string) => void
    onEvent?: (event: AgentEventEnvelope) => void
  },
): void {
  callbacks.onEvent?.(parsed)

  const isDelta = parsed.type === 'token' || parsed.type === 'message.delta'
  const isStarted = parsed.type === 'intent' || parsed.type === 'run.started'
  const isCompleted = parsed.type === 'full' || parsed.type === 'run.completed'
  const isFailed = parsed.type === 'error' || parsed.type === 'run.failed'

  if (isStarted) {
    const dataObj = typeof parsed.data === 'object' && parsed.data !== null ? (parsed.data as Record<string, unknown>) : null
    const detectedIntent = parsed.intent || (dataObj?.task_profile ? String(dataObj.task_profile) : '')
    if (detectedIntent) callbacks.onIntent?.(detectedIntent)
  } else if (isDelta) {
    const dataObj = typeof parsed.data === 'object' && parsed.data !== null ? (parsed.data as Record<string, unknown>) : null
    const chunk = parsed.text || (dataObj?.delta ? String(dataObj.delta) : '')
    if (chunk) {
      state.accumulatedText += chunk
      callbacks.onChunk(state.accumulatedText, chunk)
    }
  } else if (isCompleted) {
    state.fullResponseData = (parsed.data as AgenticPromptResponse) ?? null
    if (state.fullResponseData?.document_updates || state.fullResponseData?.answer) {
      state.accumulatedText = state.fullResponseData.document_updates || state.fullResponseData.answer || ''
      callbacks.onChunk(state.accumulatedText, '')
    }
  } else if (parsed.type === 'run.cancelled') {
    throw new Error('Generacion cancelada por el usuario.')
  } else if (isFailed) {
    const dataObj = typeof parsed.data === 'object' && parsed.data !== null ? (parsed.data as Record<string, unknown>) : null
    const errMsg = parsed.message || (dataObj?.user_message ? String(dataObj.user_message) : 'Error durante la generacion.')
    throw new Error(errMsg)
  }
}

