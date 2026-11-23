import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserAsrProvider, CANCEL_GRACE_MS, type AsrWorker } from '../providers/BrowserAsrProvider'
import type { AsrRequest, WorkerInMessage, WorkerOutMessage } from '../providers/asrMessages'

class FakeWorker implements AsrWorker {
  onmessage: ((event: MessageEvent<WorkerOutMessage>) => void) | null = null
  onerror: ((event: ErrorEvent) => void) | null = null
  posted: Array<{ message: WorkerInMessage; transfer: Transferable[] }> = []
  terminated = false

  postMessage(message: WorkerInMessage, transfer: Transferable[]) {
    this.posted.push({ message, transfer })
  }

  terminate() {
    this.terminated = true
  }

  emit(message: WorkerOutMessage) {
    this.onmessage?.({ data: message } as MessageEvent<WorkerOutMessage>)
  }

  crash(message: string) {
    this.onerror?.({ message, preventDefault: () => undefined } as unknown as ErrorEvent)
  }

  transcribeIds(): string[] {
    return this.posted.flatMap(({ message }) => (message.type === 'transcribe' ? [message.payload.id] : []))
  }
}

function setup() {
  const workers: FakeWorker[] = []
  const provider = new BrowserAsrProvider(() => {
    const worker = new FakeWorker()
    workers.push(worker)
    return worker
  })
  return { provider, workers }
}

const request = (id: string): AsrRequest => ({
  id,
  audio: new Float32Array(16000),
  language: 'es',
  modelId: 'onnx-community/whisper-base',
  duration: 1,
})

const result = (id: string): WorkerOutMessage => ({
  type: 'complete',
  payload: { id, text: 'hola', segments: [{ start: 0, end: 1, text: 'hola' }], duration: 1, language: 'es', modelInfo: 'Whisper Web (CPU Wasm)', silenceTrimmedSec: 0, diarization: 'none' },
})

afterEach(() => {
  vi.useRealTimers()
})

describe('BrowserAsrProvider', () => {
  it('transfers the samples and resolves with the worker result, forwarding progress and segments', async () => {
    const { provider, workers } = setup()
    const onProgress = vi.fn()
    const onSegments = vi.fn()
    const req = request('a')
    const promise = provider.transcribe(req, { onProgress, onSegments })

    const [worker] = workers
    expect(worker.posted[0].transfer).toEqual([req.audio.buffer])
    worker.emit({ type: 'progress', payload: { id: 'a', stage: 'transcribing', stageProgress: 0.5, message: 'x' } })
    worker.emit({ type: 'segments', payload: { id: 'a', segments: [{ start: 0, end: 1, text: 'hola' }] } })
    worker.emit(result('a'))

    await expect(promise).resolves.toMatchObject({ id: 'a', text: 'hola' })
    expect(onProgress).toHaveBeenCalledTimes(1)
    expect(onSegments).toHaveBeenCalledWith([{ start: 0, end: 1, text: 'hola' }])
    expect(provider.isBusy()).toBe(false)
  })

  it('runs jobs one at a time in the same worker', async () => {
    const { provider, workers } = setup()
    const first = provider.transcribe(request('a'))
    const second = provider.transcribe(request('b'))
    expect(workers[0].transcribeIds()).toEqual(['a'])

    workers[0].emit(result('a'))
    await first
    expect(workers[0].transcribeIds()).toEqual(['a', 'b'])
    workers[0].emit(result('b'))
    await second
    expect(workers).toHaveLength(1)
  })

  it('rejects a running job at once when cancelled and waits for the worker to stop', async () => {
    const { provider, workers } = setup()
    const first = provider.transcribe(request('a'))
    const second = provider.transcribe(request('b'))

    expect(provider.cancel('a')).toBe(true)
    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    const [worker] = workers
    expect(worker.posted.at(-1)?.message).toEqual({ type: 'cancel', id: 'a' })
    // Late messages of the cancelled job are ignored and the next job waits for the acknowledgement.
    worker.emit({ type: 'progress', payload: { id: 'a', stage: 'transcribing', stageProgress: 0.9, message: 'x' } })
    expect(worker.transcribeIds()).toEqual(['a'])

    worker.emit({ type: 'cancelled', payload: { id: 'a' } })
    expect(worker.transcribeIds()).toEqual(['a', 'b'])
    expect(worker.terminated).toBe(false)
    worker.emit(result('b'))
    await expect(second).resolves.toMatchObject({ id: 'b' })
  })

  it('cancels queued jobs without sending them to the worker', async () => {
    const { provider, workers } = setup()
    const first = provider.transcribe(request('a'))
    const queued = provider.transcribe(request('b'))
    expect(provider.cancel('b')).toBe(true)
    await expect(queued).rejects.toMatchObject({ name: 'AbortError' })
    workers[0].emit(result('a'))
    await first
    expect(workers[0].transcribeIds()).toEqual(['a'])
  })

  it('cancels through an AbortSignal', async () => {
    const { provider } = setup()
    const controller = new AbortController()
    const promise = provider.transcribe(request('a'), {}, controller.signal)
    controller.abort()
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('restarts the worker when a cancelled job does not stop in time', async () => {
    vi.useFakeTimers()
    const { provider, workers } = setup()
    const first = provider.transcribe(request('a'))
    const second = provider.transcribe(request('b'))
    provider.cancel('a')
    await expect(first).rejects.toMatchObject({ name: 'AbortError' })

    vi.advanceTimersByTime(CANCEL_GRACE_MS)
    expect(workers[0].terminated).toBe(true)
    expect(workers).toHaveLength(2)
    expect(workers[1].transcribeIds()).toEqual(['b'])
    workers[1].emit(result('b'))
    await expect(second).resolves.toMatchObject({ id: 'b' })
  })

  it('rejects the running job when the worker crashes and recreates it for the next one', async () => {
    const { provider, workers } = setup()
    const first = provider.transcribe(request('a'))
    const second = provider.transcribe(request('b'))
    workers[0].crash('sin memoria')
    await expect(first).rejects.toThrow('sin memoria')
    expect(workers[0].terminated).toBe(true)
    expect(workers[1].transcribeIds()).toEqual(['b'])
    workers[1].emit({ type: 'error', payload: { id: 'b', error: 'modelo no disponible' } })
    await expect(second).rejects.toThrow('modelo no disponible')
  })
})
