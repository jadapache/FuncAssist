import { registerGpuConsumer } from '../../../core/gpu/gpuResources'
import { abortError } from '../utils/abort'
import type {
  AsrProgress,
  AsrRequest,
  AsrResult,
  AsrSegment,
  WorkerInMessage,
  WorkerOutMessage,
} from './asrMessages'

export type { AsrProgress, AsrRequest, AsrResult, AsrSegment } from './asrMessages'

export interface AsrHandlers {
  onProgress?: (progress: AsrProgress) => void
  onSegments?: (segments: AsrSegment[]) => void
}

/** The parts of a Worker the provider uses (replaceable in tests). */
export interface AsrWorker {
  postMessage: (message: WorkerInMessage, transfer: Transferable[]) => void
  terminate: () => void
  onmessage: ((event: MessageEvent<WorkerOutMessage>) => void) | null
  onerror: ((event: ErrorEvent) => void) | null
}

export type AsrWorkerFactory = () => AsrWorker

/** How long a cancelled job may keep the worker busy before the worker is restarted. */
export const CANCEL_GRACE_MS = 15000
/**
 * An idle worker is terminated after this long, freeing the GPU memory Whisper holds (WebGPU).
 * Jobs in quick succession still reuse the loaded model.
 */
export const ASR_IDLE_RELEASE_MS = 2 * 60 * 1000
export const ASR_GPU_CONSUMER = 'whisper'

interface QueuedJob {
  request: AsrRequest
  handlers: AsrHandlers
  resolve: (result: AsrResult) => void
  reject: (error: Error) => void
}

const defaultWorkerFactory: AsrWorkerFactory = () =>
  new Worker(new URL('../workers/transcription.worker.ts', import.meta.url), { type: 'module' }) as unknown as AsrWorker

/** Samples backed by their own ArrayBuffer, so they can be transferred without copying. */
function transferableSamples(audio: Float32Array): Float32Array<ArrayBuffer> {
  if (audio.buffer instanceof ArrayBuffer && audio.byteOffset === 0 && audio.byteLength === audio.buffer.byteLength) {
    return audio as Float32Array<ArrayBuffer>
  }
  return new Float32Array(audio)
}

/**
 * Runs in-browser Whisper jobs one at a time in a single long-lived worker, so the model is
 * loaded once. Cancelling rejects the job's promise immediately; the worker stops at the next
 * window and is restarted only if it does not acknowledge within CANCEL_GRACE_MS.
 */
export class BrowserAsrProvider {
  private static instance: BrowserAsrProvider | null = null

  private readonly createWorker: AsrWorkerFactory
  private worker: AsrWorker | null = null
  private queue: QueuedJob[] = []
  private current: QueuedJob | null = null
  /** Id of a cancelled job the worker is still finishing. */
  private stopping: string | null = null
  private stopTimer: ReturnType<typeof setTimeout> | null = null
  private idleTimer: ReturnType<typeof setTimeout> | null = null

  constructor(createWorker: AsrWorkerFactory = defaultWorkerFactory) {
    this.createWorker = createWorker
  }

  public static getInstance(): BrowserAsrProvider {
    if (!BrowserAsrProvider.instance) {
      const provider = new BrowserAsrProvider()
      // The in-browser LLM asks for the GPU before loading: give it up if no job is running.
      registerGpuConsumer(ASR_GPU_CONSUMER, () => {
        provider.releaseIfIdle()
      })
      BrowserAsrProvider.instance = provider
    }
    return BrowserAsrProvider.instance
  }

  /** Terminates the worker (and its GPU memory) when no job is running or queued. */
  public releaseIfIdle(): boolean {
    if (this.current || this.stopping || this.queue.length > 0) return false
    this.clearIdleTimer()
    this.disposeWorker()
    return true
  }

  private clearIdleTimer(): void {
    if (this.idleTimer) clearTimeout(this.idleTimer)
    this.idleTimer = null
  }

  private scheduleIdleRelease(): void {
    if (!this.worker) return
    this.clearIdleTimer()
    this.idleTimer = setTimeout(() => {
      this.idleTimer = null
      this.releaseIfIdle()
    }, ASR_IDLE_RELEASE_MS)
  }

  public transcribe(request: AsrRequest, handlers: AsrHandlers = {}, signal?: AbortSignal): Promise<AsrResult> {
    return new Promise<AsrResult>((resolve, reject) => {
      if (signal?.aborted) {
        reject(abortError())
        return
      }
      signal?.addEventListener('abort', () => this.cancel(request.id), { once: true })
      this.queue.push({ request, handlers, resolve, reject })
      this.pump()
    })
  }

  /** Cancels a queued or running job. Its promise rejects with an AbortError right away. */
  public cancel(id: string): boolean {
    const index = this.queue.findIndex((job) => job.request.id === id)
    if (index >= 0) {
      const [job] = this.queue.splice(index, 1)
      job.reject(abortError())
      return true
    }
    if (this.current?.request.id !== id) return false

    const job = this.current
    this.current = null
    job.reject(abortError())
    this.stopping = id
    this.worker?.postMessage({ type: 'cancel', id }, [])
    this.stopTimer = setTimeout(() => this.restartWorker(), CANCEL_GRACE_MS)
    return true
  }

  public isBusy(): boolean {
    return Boolean(this.current || this.stopping || this.queue.length > 0)
  }

  private pump(): void {
    if (this.current || this.stopping) return
    if (this.queue.length === 0) {
      this.scheduleIdleRelease()
      return
    }
    this.clearIdleTimer()
    const job = this.queue.shift() as QueuedJob
    this.current = job
    const audio = transferableSamples(job.request.audio)
    const payload: AsrRequest = { ...job.request, audio }
    try {
      this.ensureWorker().postMessage({ type: 'transcribe', payload }, [audio.buffer])
    } catch (err) {
      this.current = null
      job.reject(err instanceof Error ? err : new Error(String(err)))
      this.pump()
    }
  }

  private ensureWorker(): AsrWorker {
    if (!this.worker) {
      const worker = this.createWorker()
      worker.onmessage = (event) => this.handleMessage(event.data)
      worker.onerror = (event) => {
        event.preventDefault?.()
        this.handleCrash(event.message || 'El motor de transcripción del navegador se detuvo inesperadamente.')
      }
      this.worker = worker
    }
    return this.worker
  }

  private finishStopping(id: string): void {
    if (this.stopping !== id) return
    this.stopping = null
    if (this.stopTimer) clearTimeout(this.stopTimer)
    this.stopTimer = null
    this.pump()
  }

  private handleMessage(message: WorkerOutMessage): void {
    const current = this.current
    switch (message.type) {
      case 'progress':
        if (current?.request.id === message.payload.id) current.handlers.onProgress?.(message.payload)
        return
      case 'segments':
        if (current?.request.id === message.payload.id) current.handlers.onSegments?.(message.payload.segments)
        return
      case 'complete':
        if (current?.request.id === message.payload.id) {
          this.current = null
          current.resolve(message.payload)
          this.pump()
        } else {
          this.finishStopping(message.payload.id)
        }
        return
      case 'error':
        if (current?.request.id === message.payload.id) {
          this.current = null
          current.reject(new Error(message.payload.error || 'Error durante la transcripción en el navegador.'))
          this.pump()
        } else {
          this.finishStopping(message.payload.id)
        }
        return
      case 'cancelled':
        this.finishStopping(message.payload.id)
        return
    }
  }

  private handleCrash(reason: string): void {
    const job = this.current
    this.current = null
    this.disposeWorker()
    job?.reject(new Error(reason))
    this.pump()
  }

  private restartWorker(): void {
    this.disposeWorker()
    this.pump()
  }

  private disposeWorker(): void {
    this.worker?.terminate()
    this.worker = null
    this.stopping = null
    if (this.stopTimer) clearTimeout(this.stopTimer)
    this.stopTimer = null
  }
}

export const browserAsrProvider = BrowserAsrProvider.getInstance()
