import {
  API_BASE,
  handleResponse,
  type AgenticPromptResponse,
} from '../../../api/client'

export const docAgentApi = {
  agenticPrompt: (payload: {
    query: string
    current_document?: string
    chat_context?: string[]
    sources?: string[]
    document_ids?: string[]
    template_id?: string
  }): Promise<AgenticPromptResponse> =>
    fetch(`${API_BASE}/api/doc-agent/agentic-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: payload.query,
        query: payload.query,
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

  agenticPromptStream: async (
    payload: {
      query: string
      current_document?: string
      chat_context?: string[]
      sources?: string[]
      document_ids?: string[]
      template_id?: string
    },
    onChunk: (accumulatedText: string, chunk: string) => void,
  ): Promise<AgenticPromptResponse> => {
    const res = await fetch(`${API_BASE}/api/doc-agent/agentic-prompt-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: payload.query,
        query: payload.query,
        current_document: payload.current_document,
        chat_context: payload.chat_context,
        sources: payload.sources,
        document_ids: payload.document_ids,
        templateId: payload.template_id,
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
    let accumulatedText = ''
    let buffer = ''
    let fullResponseData: any = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          let parsed: any = null
          try {
            parsed = JSON.parse(trimmed.slice(6))
          } catch {
            // ignore JSON parse errors for incomplete data lines
            continue
          }

          if (parsed.type === 'token') {
            const chunk = parsed.text || ''
            accumulatedText += chunk
            onChunk(accumulatedText, chunk)
          } else if (parsed.type === 'full') {
            fullResponseData = parsed.data
            if (parsed.data?.document_updates || parsed.data?.answer) {
              accumulatedText = parsed.data.document_updates || parsed.data.answer
              onChunk(accumulatedText, '')
            }
          } else if (parsed.type === 'error') {
            throw new Error(parsed.message || 'Error durante la generación.')
          }
        }
      }
    }

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

    if (!accumulatedText.trim()) {
      throw new Error(
        'El modelo no devolvió ninguna respuesta o la conexión falló. Verifica tu API Key y la configuración del modelo.',
      )
    }

    return {
      answer: accumulatedText,
      document_updates: accumulatedText,
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
