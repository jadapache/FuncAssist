import { describe, expect, it, vi } from 'vitest'
import { openProgressStream, type ProgressStreamOptions } from '../api/progressStream'
import type { TranscriptionProgress } from '../api/transcriptionApi'

const encoder = new TextEncoder()

const frame = (data: object, event = 'progress') => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

/** Minimal Response whose body yields the given chunks and then ends (or hangs). */
function sseResponse(chunks: string[], options: { hang?: boolean; status?: number } = {}): Response {
  let index = 0
  const status = options.status ?? 200
  return {
    ok: status >= 200 && status < 300,
    status,
    body: {
      getReader: () => ({
        read: () =>
          index < chunks.length
            ? Promise.resolve({ done: false, value: encoder.encode(chunks[index++]) })
            : options.hang
              ? new Promise(() => undefined)
              : Promise.resolve({ done: true, value: undefined }),
        cancel: () => Promise.resolve(),
      }),
    },
  } as unknown as Response
}

const progress = (seq: number, stage: string, extra: Partial<TranscriptionProgress> = {}) => ({
  id: 'job1',
  media_id: 'job1',
  stage,
  status: stage,
  progress: stage === 'complete' ? 100 : 40,
  seq,
  ...extra,
})

const baseOptions = (fetchImpl: ProgressStreamOptions['fetchImpl']): ProgressStreamOptions => ({
  url: '/stream',
  fetchImpl,
  headers: () => ({ Authorization: 'Bearer t' }),
  sleep: () => Promise.resolve(),
  statusFetcher: () => Promise.reject(new Error('unused')),
})

describe('openProgressStream', () => {
  it('delivers progress, ignores heartbeats and finishes on a terminal stage', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      sseResponse([
        frame(progress(1, 'transcribing')),
        frame({}, 'heartbeat'),
        frame(progress(2, 'complete', { summary_status: 'done' })),
      ]),
    )
    const onProgress = vi.fn()
    const onFinished = vi.fn()
    const handle = openProgressStream('job1', { onProgress, onFinished }, baseOptions(fetchImpl))

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalledTimes(1))
    expect(onProgress.mock.calls.map(([p]) => p.seq)).toEqual([1, 2])
    expect(onFinished.mock.calls[0][0].stage).toBe('complete')
    expect(handle.isClosed()).toBe(true)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    const [, init] = fetchImpl.mock.calls[0]
    expect(init.headers.Authorization).toBe('Bearer t')
  })

  it('reconnects with Last-Event-ID and drops duplicated seq values', async () => {
    const fetchImpl = vi
      .fn()
      // Legacy unnamed frames are accepted too.
      .mockResolvedValueOnce(sseResponse([`data: ${JSON.stringify(progress(1, 'transcribing'))}\n\n`, frame(progress(2, 'transcribing'))]))
      .mockResolvedValueOnce(sseResponse([frame(progress(2, 'transcribing')), frame(progress(3, 'failed', { error: 'boom' }))]))
    const onProgress = vi.fn()
    const onFinished = vi.fn()
    openProgressStream('job1', { onProgress, onFinished }, baseOptions(fetchImpl))

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled())
    expect(onProgress.mock.calls.map(([p]) => p.seq)).toEqual([1, 2, 3])
    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(fetchImpl.mock.calls[1][1].headers['Last-Event-ID']).toBe('2')
  })

  it('accepts a terminal stage after a restart even when seq did not grow', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(sseResponse([frame(progress(7, 'transcribing'))]))
      .mockResolvedValueOnce(sseResponse([frame(progress(1, 'interrupted'))]))
    const onFinished = vi.fn()
    openProgressStream('job1', { onProgress: vi.fn(), onFinished }, baseOptions(fetchImpl))
    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled())
    expect(onFinished.mock.calls[0][0].stage).toBe('interrupted')
  })

  it('stays open after complete while the summary runs', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      sseResponse([
        frame(progress(1, 'complete', { summary_status: 'running' })),
        frame(progress(2, 'complete', { summary_status: 'done' })),
      ]),
    )
    const onFinished = vi.fn()
    const onProgress = vi.fn()
    openProgressStream('job1', { onProgress, onFinished }, baseOptions(fetchImpl))
    await vi.waitFor(() => expect(onFinished).toHaveBeenCalledTimes(1))
    expect(onProgress).toHaveBeenCalledTimes(2)
    expect(onFinished.mock.calls[0][0].summary_status).toBe('done')
  })

  it('reports a missing job and stops', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse([], { status: 404 }))
    const onNotFound = vi.fn()
    const handle = openProgressStream('job1', { onProgress: vi.fn(), onNotFound }, baseOptions(fetchImpl))
    await vi.waitFor(() => expect(onNotFound).toHaveBeenCalled())
    expect(handle.isClosed()).toBe(true)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('polls /status after repeated connection failures', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('network down'))
    const statusFetcher = vi.fn().mockResolvedValue(progress(5, 'failed', { error: 'sin red' }))
    const onFinished = vi.fn()
    openProgressStream(
      'job1',
      { onProgress: vi.fn(), onFinished },
      { ...baseOptions(fetchImpl), statusFetcher, pollAfterFailures: 2 },
    )
    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled())
    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(statusFetcher).toHaveBeenCalledTimes(1)
  })

  it('backs off between attempts and can be closed', async () => {
    const delays: number[] = []
    let calls = 0
    const fetchImpl = vi.fn().mockImplementation(() => {
      calls += 1
      return Promise.reject(new TypeError('down'))
    })
    const handle = openProgressStream(
      'job1',
      { onProgress: vi.fn() },
      {
        ...baseOptions(fetchImpl),
        pollAfterFailures: 99,
        backoffMs: [1, 2, 4],
        sleep: (ms) => {
          delays.push(ms)
          if (delays.length >= 4) handle.close()
          return Promise.resolve()
        },
      },
    )
    await vi.waitFor(() => expect(handle.isClosed()).toBe(true))
    expect(delays.slice(0, 4)).toEqual([1, 2, 4, 4])
    expect(calls).toBe(4)
  })
})
