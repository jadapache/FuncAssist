import type { AgenticPromptResponse } from '../../../api/client'
import type { AgentEventEnvelope } from '../types/agentEvents'

/** One server-sent event: `event:` name (empty for legacy `data:`-only frames) and raw `data:`. */
export interface SseFrame {
  event: string
  data: string
}

/**
 * Incremental SSE parser. Feed decoded text; complete frames (terminated by a blank line) are
 * returned, partial ones are kept for the next call.
 */
export class SseFrameParser {
  private buffer = ''

  feed(text: string): SseFrame[] {
    this.buffer += text.replace(/\r\n/g, '\n')
    const frames: SseFrame[] = []
    let sep = this.buffer.indexOf('\n\n')
    while (sep >= 0) {
      const raw = this.buffer.slice(0, sep)
      this.buffer = this.buffer.slice(sep + 2)
      const frame = parseFrame(raw)
      if (frame) frames.push(frame)
      sep = this.buffer.indexOf('\n\n')
    }
    return frames
  }

  /** Frame left without its trailing blank line when the stream closed. */
  flush(): SseFrame[] {
    const frame = parseFrame(this.buffer)
    this.buffer = ''
    return frame ? [frame] : []
  }
}

function parseFrame(raw: string): SseFrame | null {
  let event = ''
  const data: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  return data.length ? { event, data: data.join('\n') } : null
}

export interface StreamState {
  accumulatedText: string
  fullResponseData: AgenticPromptResponse | null
  /** Step opened by the latest `status` event, closed when the next stage starts or the run ends. */
  openStatusStep: string | null
}

export interface StreamCallbacks {
  onChunk: (accumulatedText: string, chunk: string) => void
  onIntent?: (intent: string) => void
  onEvent?: (event: AgentEventEnvelope) => void
}

type Data = Record<string, unknown>

const str = (value: unknown, fallback = ''): string =>
  value === undefined || value === null ? fallback : String(value)

function escapeAttr(value: string): string {
  return value.replace(/"/g, "'")
}

export class StreamError extends Error {
  readonly code: string

  constructor(message: string, code: string) {
    super(message)
    this.code = code
  }
}

function appendText(state: StreamState, text: string, callbacks: StreamCallbacks) {
  if (!text) return
  state.accumulatedText += text
  callbacks.onChunk(state.accumulatedText, text)
}

function closeStatusStep(state: StreamState, callbacks: StreamCallbacks) {
  if (!state.openStatusStep) return
  callbacks.onEvent?.({ type: 'run.step.completed', data: { step_id: state.openStatusStep, label: '' } })
  state.openStatusStep = null
}

/**
 * Apply one protocol-v2 event: rebuild the raw answer text (with `<artifact>` markup, which the chat
 * UI parses) and translate progress events into the run envelopes the UI hooks already consume.
 * Throws `StreamError` on `error` events.
 */
export function applyV2Event(
  eventName: string,
  data: Data,
  state: StreamState,
  callbacks: StreamCallbacks,
): void {
  const emit = (event: AgentEventEnvelope) => callbacks.onEvent?.(event)

  switch (eventName) {
    case 'status': {
      if (data.stage === 'classify') {
        const intent = str(data.intent)
        emit({
          type: 'run.started',
          run_id: str(data.run_id) || undefined,
          conversation_id: str(data.conversation_id) || undefined,
          data: { task_profile: intent || 'general' },
        })
        if (intent) callbacks.onIntent?.(intent)
        return
      }
      if (data.stage === 'section') {
        const stepId = `step-section-${str(data.section_index, '0')}`
        const label = `Sección: ${str(data.section_title)}`
        emit({ type: data.pending ? 'run.step.failed' : 'run.step.completed', data: { step_id: stepId, label } })
        return
      }
      const stepId = `step-${str(data.stage, 'status')}`
      if (state.openStatusStep !== stepId) closeStatusStep(state, callbacks)
      state.openStatusStep = stepId
      emit({ type: 'run.step.started', data: { step_id: stepId, label: str(data.message, 'Procesando...') } })
      return
    }
    case 'plan': {
      const sections = Array.isArray(data.sections) ? data.sections : []
      sections.forEach((title, index) => {
        emit({ type: 'run.step.started', data: { step_id: `step-section-${index}`, label: `Sección: ${str(title)}` } })
      })
      return
    }
    case 'tool_call':
      emit({
        type: 'run.step.started',
        data: { step_id: `step-tool-${str(data.id)}`, label: `Usando herramienta: ${str(data.name)}` },
      })
      return
    case 'tool_result':
      emit({
        type: data.is_error ? 'run.step.failed' : 'run.step.completed',
        data: { step_id: `step-tool-${str(data.id)}`, label: `Herramienta ${str(data.name)} finalizada` },
      })
      return
    case 'delta':
      appendText(state, str(data.text), callbacks)
      return
    case 'artifact_start':
      appendText(
        state,
        `<artifact title="${escapeAttr(str(data.title, 'Documento'))}" extension="${escapeAttr(str(data.extension, 'docx'))}">\n`,
        callbacks,
      )
      return
    case 'artifact_delta':
      appendText(state, str(data.text), callbacks)
      return
    case 'artifact_end':
      appendText(state, '\n</artifact>\n', callbacks)
      return
    case 'usage':
      return
    case 'error': {
      closeStatusStep(state, callbacks)
      const code = str(data.code, 'error')
      if (code === 'cancelled') {
        emit({ type: 'run.cancelled', data })
        throw new StreamError('Generacion cancelada por el usuario.', code)
      }
      const message = str(data.message, 'Error durante la generacion.')
      emit({ type: 'run.failed', data: { error_code: code, user_message: message } })
      throw new StreamError(message, code)
    }
    case 'done': {
      closeStatusStep(state, callbacks)
      const response = data as unknown as AgenticPromptResponse
      state.fullResponseData = response
      const artifacts = Array.isArray(data.artifacts) ? (data.artifacts as Data[]) : []
      artifacts.forEach((art, idx) => {
        emit({
          type: 'artifact.created',
          data: {
            artifact_id: str(art.id) || `art-${idx + 1}`,
            title: str(art.title, 'Documento'),
            extension: str(art.extension, 'docx'),
            content: str(art.content),
          },
        })
      })
      emit({ type: 'run.completed', data: { final_message: str(data.assistant_message) } })
      const finalText = response.document_updates || response.answer
      if (finalText) {
        state.accumulatedText = finalText
        callbacks.onChunk(state.accumulatedText, '')
      }
      return
    }
    default:
      return
  }
}
