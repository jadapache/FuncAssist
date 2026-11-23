import { describe, expect, it, vi } from 'vitest'
import { SseFrameParser, StreamError, applyV2Event, type StreamState } from './sseV2'
import type { AgentEventEnvelope } from '../types/agentEvents'

const newState = (): StreamState => ({ accumulatedText: '', fullResponseData: null, openStatusStep: null })

describe('SseFrameParser', () => {
  it('joins frames split across network chunks', () => {
    const parser = new SseFrameParser()
    expect(parser.feed('event: delta\ndata: {"te')).toEqual([])
    expect(parser.feed('xt":"ho"}\n\nevent: delta\ndata: {"text":"la"}\n\n')).toEqual([
      { event: 'delta', data: '{"text":"ho"}' },
      { event: 'delta', data: '{"text":"la"}' },
    ])
  })

  it('keeps legacy data-only frames with an empty event name', () => {
    const parser = new SseFrameParser()
    expect(parser.feed('data: {"type":"token","text":"x"}\n\n')).toEqual([
      { event: '', data: '{"type":"token","text":"x"}' },
    ])
  })

  it('flushes a final frame without trailing blank line', () => {
    const parser = new SseFrameParser()
    parser.feed('event: done\ndata: {}')
    expect(parser.flush()).toEqual([{ event: 'done', data: '{}' }])
  })
})

describe('applyV2Event', () => {
  it('rebuilds artifact markup for the chat UI parser', () => {
    const state = newState()
    const onChunk = vi.fn()
    const cb = { onChunk }
    applyV2Event('delta', { text: 'Listo.' }, state, cb)
    applyV2Event('artifact_start', { index: 0, title: 'Plan "QA"', extension: 'docx' }, state, cb)
    applyV2Event('artifact_delta', { index: 0, text: '# Hola' }, state, cb)
    applyV2Event('artifact_end', { index: 0 }, state, cb)
    expect(state.accumulatedText).toBe('Listo.<artifact title="Plan \'QA\'" extension="docx">\n# Hola\n</artifact>\n')
    expect(onChunk).toHaveBeenCalledTimes(4)
  })

  it('maps progress events onto run envelopes and reports the intent', () => {
    const state = newState()
    const events: AgentEventEnvelope[] = []
    const onIntent = vi.fn()
    const cb = { onChunk: vi.fn(), onIntent, onEvent: (e: AgentEventEnvelope) => events.push(e) }
    applyV2Event('status', { stage: 'classify', intent: 'generic_plan', run_id: 'r1' }, state, cb)
    applyV2Event('status', { stage: 'context', message: 'Preparando contexto...' }, state, cb)
    applyV2Event('plan', { sections: ['Alcance', 'Riesgos'] }, state, cb)
    applyV2Event('status', { stage: 'section', section_index: 1, section_title: 'Riesgos', pending: true }, state, cb)
    applyV2Event('status', { stage: 'sections', message: 'Redactando' }, state, cb)

    expect(onIntent).toHaveBeenCalledWith('generic_plan')
    expect(events.map((e) => e.type)).toEqual([
      'run.started',
      'run.step.started', // context
      'run.step.started', // section 0
      'run.step.started', // section 1
      'run.step.failed', // section 1 pending
      'run.step.completed', // context closed when the next stage starts
      'run.step.started', // sections
    ])
  })

  it('stores the final response and emits created artifacts on done', () => {
    const state = newState()
    const events: AgentEventEnvelope[] = []
    const cb = { onChunk: vi.fn(), onEvent: (e: AgentEventEnvelope) => events.push(e) }
    applyV2Event(
      'done',
      { answer: 'raw', assistant_message: 'ok', artifacts: [{ title: 'Plan', extension: 'docx', content: '# P' }] },
      state,
      cb,
    )
    expect(state.fullResponseData?.assistant_message).toBe('ok')
    expect(state.accumulatedText).toBe('raw')
    expect(events.map((e) => e.type)).toEqual(['artifact.created', 'run.completed'])
  })

  it('throws typed errors, including cancellation', () => {
    const cb = { onChunk: vi.fn() }
    expect(() => applyV2Event('error', { code: 'rate_limit', message: 'Espera' }, newState(), cb)).toThrow('Espera')
    try {
      applyV2Event('error', { code: 'cancelled' }, newState(), cb)
    } catch (err) {
      expect(err).toBeInstanceOf(StreamError)
      expect((err as StreamError).code).toBe('cancelled')
    }
  })
})
