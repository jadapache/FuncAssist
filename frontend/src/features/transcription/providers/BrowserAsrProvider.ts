export interface AsrProgressPayload {
  progress: number
  stage: string
  message: string
  eta?: string | null
  live_text?: string
  live_segments?: Array<{ start: number; end: number; speaker: string; text: string }>
  model_info?: string
}

export interface AsrCompletePayload {
  id: string
  text: string
  segments: Array<{ start: number; end: number; speaker: string; text: string }>
  duration: number
  language: string
  model_info: string
}

export interface TranscribeRequestPayload {
  id: string
  audioData: Float32Array
  language: string
  modelId: string
  duration: number
}

export class BrowserAsrProvider {
  private static instance: BrowserAsrProvider | null = null
  private worker: Worker | null = null
  private activeJobId: string | null = null

  public static getInstance(): BrowserAsrProvider {
    if (!BrowserAsrProvider.instance) {
      BrowserAsrProvider.instance = new BrowserAsrProvider()
    }
    return BrowserAsrProvider.instance
  }

  private ensureWorker(): Worker {
    if (!this.worker) {
      this.worker = new Worker(
        new URL('../workers/transcription.worker.ts', import.meta.url),
        { type: 'module' },
      )
    }
    return this.worker
  }

  public getActiveJobId(): string | null {
    return this.activeJobId
  }

  public cancelActiveJob(): void {
    if (this.worker) {
      this.worker.terminate()
      this.worker = null
    }
    this.activeJobId = null
  }

  public async transcribe(
    payload: TranscribeRequestPayload,
    onProgress: (progress: AsrProgressPayload) => void,
    isCancelled: () => boolean,
    onRegisterWorker?: (worker: Worker) => void,
  ): Promise<AsrCompletePayload> {
    this.cancelActiveJob()
    const worker = this.ensureWorker()
    this.activeJobId = payload.id
    onRegisterWorker?.(worker)

    return new Promise<AsrCompletePayload>((resolve, reject) => {
      worker.onmessage = (event: MessageEvent) => {
        if (isCancelled()) {
          this.cancelActiveJob()
          reject(new Error('Transcripción cancelada por el usuario.'))
          return
        }

        const { type, payload: resPayload } = event.data
        if (type === 'progress') {
          onProgress(resPayload as AsrProgressPayload)
          return
        }
        if (type === 'complete') {
          this.activeJobId = null
          resolve(resPayload as AsrCompletePayload)
          return
        }
        if (type === 'error') {
          this.cancelActiveJob()
          reject(new Error(resPayload?.error || 'Error durante la inferencia ASR en navegador.'))
        }
      }

      worker.onerror = (err) => {
        this.cancelActiveJob()
        reject(err)
      }

      worker.postMessage({ type: 'transcribe', payload })
    })
  }

  public terminate(): void {
    this.cancelActiveJob()
  }
}

export const browserAsrProvider = BrowserAsrProvider.getInstance()
