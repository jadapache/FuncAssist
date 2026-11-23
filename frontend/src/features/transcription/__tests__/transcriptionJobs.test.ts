import { describe, expect, it } from 'vitest'
import { createJob, jobsReducer, type JobsState } from '../context/transcriptionJobs'
import type { TranscriptionProgress } from '../api/transcriptionApi'

const started = (): JobsState =>
  jobsReducer({}, { type: 'start', now: 100, job: { id: 'j1', kind: 'server', title: 'Kickoff', stage: 'uploading' } })

const event = (seq: number, stage: TranscriptionProgress['stage'], progress: number, extra: Partial<TranscriptionProgress> = {}) => ({
  type: 'server_progress' as const,
  progress: { id: 'j1', stage, progress, seq, ...extra },
})

describe('jobsReducer', () => {
  it('creates jobs with the given kind and start time', () => {
    const state = started()
    expect(state.j1).toMatchObject({ kind: 'server', title: 'Kickoff', stage: 'uploading', progress: 0, startedAt: 100 })
    expect(state.j1.liveSegments).toEqual([])
  })

  it('never lets the overall progress go back while running', () => {
    let state = jobsReducer(started(), { type: 'update', id: 'j1', patch: { progress: 20, stage: 'uploading' } })
    state = jobsReducer(state, event(1, 'queued', 10))
    expect(state.j1.progress).toBe(20)
    state = jobsReducer(state, event(2, 'transcribing', 45))
    expect(state.j1).toMatchObject({ stage: 'transcribing', status: 'transcribing', progress: 45 })
  })

  it('ignores duplicated or older events', () => {
    let state = jobsReducer(started(), event(5, 'transcribing', 50, { message: 'nuevo' }))
    state = jobsReducer(state, event(4, 'transcribing', 60, { message: 'viejo' }))
    state = jobsReducer(state, event(5, 'transcribing', 70, { message: 'repetido' }))
    expect(state.j1).toMatchObject({ progress: 50, message: 'nuevo' })
  })

  it('accepts a new terminal stage even without a higher seq (restart)', () => {
    let state = jobsReducer(started(), event(9, 'transcribing', 50))
    state = jobsReducer(state, event(1, 'interrupted', 0, { error: 'reinicio', retryable: true }))
    expect(state.j1).toMatchObject({ stage: 'interrupted', progress: 50, retryable: true, error: 'reinicio' })
  })

  it('sets 100 on complete and clears the ETA on terminal stages', () => {
    let state = jobsReducer(started(), event(1, 'transcribing', 40, { eta_seconds: 30, eta: '~30 s' }))
    state = jobsReducer(state, event(2, 'complete', 99))
    expect(state.j1).toMatchObject({ progress: 100, eta: null, eta_seconds: null })
  })

  it('starts over when a terminal job runs again (retry)', () => {
    let state = jobsReducer(started(), event(3, 'failed', 0, { error: 'boom' }))
    state = jobsReducer(state, { type: 'hide_toast', id: 'j1' })
    state = jobsReducer(state, { type: 'update', id: 'j1', patch: { stage: 'queued', progress: 10 } })
    expect(state.j1).toMatchObject({ stage: 'queued', progress: 10, error: null, toastHidden: false })
  })

  it('maps legacy stage names', () => {
    const state = jobsReducer(started(), event(1, 'pending' as TranscriptionProgress['stage'], 5))
    expect(state.j1.stage).toBe('queued')
  })

  it('only creates unknown jobs from server events when asked to (restore)', () => {
    const ignored = jobsReducer({}, event(1, 'transcribing', 30))
    expect(ignored).toEqual({})
    const restored = jobsReducer({}, { ...event(1, 'transcribing', 30), title: 'Guardada', create: true, now: 5 })
    expect(restored.j1).toMatchObject({ kind: 'server', title: 'Guardada', progress: 30, startedAt: 5 })
  })

  it('appends live segments and removes or resets jobs', () => {
    let state = jobsReducer(
      { j2: createJob({ id: 'j2', kind: 'browser', title: 'Local', stage: 'transcribing' }, 1) },
      { type: 'append_segments', id: 'j2', segments: [{ start: 0, end: 1, speaker: 'Participante 1', text: 'hola' }] },
    )
    state = jobsReducer(state, {
      type: 'append_segments',
      id: 'j2',
      segments: [{ start: 1, end: 2, speaker: 'Participante 1', text: 'mundo' }],
    })
    expect(state.j2.liveSegments.map((s) => s.text)).toEqual(['hola', 'mundo'])
    expect(jobsReducer(state, { type: 'remove', id: 'j2' })).toEqual({})
    expect(jobsReducer(state, { type: 'reset' })).toEqual({})
  })
})
