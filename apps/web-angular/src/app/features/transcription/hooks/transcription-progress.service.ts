import { Injectable, Injector, effect, inject, signal, untracked, type Signal } from '@angular/core'
import { transcriptionApi } from '../api/transcriptionApi'

export interface TranscriptionProgressData {
  stage: string
  progress: number
  message: string
  preview?: string | null
  eta?: string | null
  model_info?: string | null
  error?: string | null
  event?: string
  timestamp?: string
}

/**
 * Angular port of React `useTranscriptionProgress`: subscribes to real-time transcription progress
 * via Server-Sent Events (SSE).
 *
 * Per-component service (list it in the consumer's `providers`) — call {@link init} with the
 * transcription id signal. It connects on init / id change, disconnects on destroy or id change,
 * and reconnects with exponential backoff (max 5 attempts, 15 s cap), exactly like the React hook.
 */
@Injectable()
export class TranscriptionProgressService {
  private readonly injector = inject(Injector)
  private initialized = false

  private readonly _progress = signal<number>(0)
  private readonly _stage = signal<string>('pending')
  private readonly _message = signal<string>('')
  private readonly _preview = signal<string>('')
  private readonly _eta = signal<string>('')
  private readonly _modelInfo = signal<string>('')
  private readonly _isComplete = signal<boolean>(false)
  private readonly _isFailed = signal<boolean>(false)
  private readonly _error = signal<string | null>(null)
  private readonly _isConnected = signal<boolean>(false)

  readonly progress = this._progress.asReadonly()
  readonly stage = this._stage.asReadonly()
  readonly message = this._message.asReadonly()
  readonly preview = this._preview.asReadonly()
  readonly eta = this._eta.asReadonly()
  readonly modelInfo = this._modelInfo.asReadonly()
  readonly isComplete = this._isComplete.asReadonly()
  readonly isFailed = this._isFailed.asReadonly()
  readonly error = this._error.asReadonly()
  readonly isConnected = this._isConnected.asReadonly()

  /** Hook parameter `transcriptionId`. */
  init(transcriptionId: Signal<string | null>): void {
    if (this.initialized) return
    this.initialized = true

    effect(
      (onCleanup) => {
        const id = transcriptionId()
        untracked(() => {
          const dispose = this.subscribe(id)
          if (dispose) onCleanup(dispose)
        })
      },
      { injector: this.injector },
    )
  }

  private subscribe(transcriptionId: string | null): (() => void) | undefined {
    if (!transcriptionId) {
      this._progress.set(0)
      this._stage.set('pending')
      this._message.set('')
      this._preview.set('')
      this._isComplete.set(false)
      this._isFailed.set(false)
      this._error.set(null)
      this._isConnected.set(false)
      return undefined
    }

    let eventSource: EventSource | null = null
    let reconnectAttempts = 0
    const maxReconnectAttempts = 5
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let isDisposed = false

    const connect = () => {
      if (isDisposed) return

      try {
        const streamUrl = transcriptionApi.getProgressStreamUrl(transcriptionId)
        eventSource = new EventSource(streamUrl)

        eventSource.addEventListener('open', () => {
          if (isDisposed) return
          this._isConnected.set(true)
          this._error.set(null)
          reconnectAttempts = 0
        })

        eventSource.addEventListener('message', (event) => {
          if (isDisposed) return
          try {
            const data = JSON.parse(event.data) as TranscriptionProgressData

            // Skip internal heartbeat
            if (data.stage === 'heartbeat' || data.event === 'heartbeat') {
              return
            }
            // Skip raw connected event
            if (data.event === 'connected') {
              return
            }

            const currentStage = data.stage || 'processing'
            this._progress.set(typeof data.progress === 'number' ? data.progress : 0)
            this._stage.set(currentStage)
            this._message.set(data.message || '')
            if (data.preview) this._preview.set(data.preview)
            if (data.eta) this._eta.set(data.eta)
            if (data.model_info) this._modelInfo.set(data.model_info)

            if (currentStage === 'complete' || data.progress === 100) {
              this._isComplete.set(true)
              this._isFailed.set(false)
            } else if (currentStage === 'failed') {
              this._isFailed.set(true)
              this._error.set(data.error || data.message || 'Error en el proceso de transcripción')
            }
          } catch (err) {
            console.warn('Error parsing SSE progress packet:', err)
          }
        })

        eventSource.addEventListener('error', () => {
          if (isDisposed) return
          this._isConnected.set(false)

          if (eventSource?.readyState === EventSource.CLOSED) {
            if (reconnectAttempts < maxReconnectAttempts) {
              reconnectAttempts++
              const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 15000)
              reconnectTimer = setTimeout(() => {
                if (!isDisposed) connect()
              }, delay)
            } else {
              this._error.set('Conexión con el flujo en tiempo real perdida')
            }
          }

          if (eventSource) {
            eventSource.close()
            eventSource = null
          }
        })
      } catch (err) {
        console.warn('Could not establish EventSource:', err)
        this._isConnected.set(false)
      }
    }

    connect()

    return () => {
      isDisposed = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
    }
  }
}
