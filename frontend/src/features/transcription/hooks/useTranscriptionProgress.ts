import { useState, useEffect } from 'react'
import { API_BASE } from '../../../api/client'

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
 * Hook that subscribes to real-time transcription progress via Server-Sent Events (SSE).
 * 
 * Automatically connects to the SSE stream on mount and disconnects on unmount.
 * Handles reconnection with exponential backoff.
 */
export function useTranscriptionProgress(transcriptionId: string | null) {
  const [progress, setProgress] = useState<number>(0)
  const [stage, setStage] = useState<string>('pending')
  const [message, setMessage] = useState<string>('')
  const [preview, setPreview] = useState<string>('')
  const [eta, setEta] = useState<string>('')
  const [modelInfo, setModelInfo] = useState<string>('')
  const [isComplete, setIsComplete] = useState<boolean>(false)
  const [isFailed, setIsFailed] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState<boolean>(false)

  useEffect(() => {
    if (!transcriptionId) {
      setProgress(0)
      setStage('pending')
      setMessage('')
      setPreview('')
      setIsComplete(false)
      setIsFailed(false)
      setError(null)
      setIsConnected(false)
      return
    }

    let eventSource: EventSource | null = null
    let reconnectAttempts = 0
    const maxReconnectAttempts = 5
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let isDisposed = false

    const connect = () => {
      if (isDisposed) return

      try {
        const streamUrl = `${API_BASE}/api/transcription/progress-stream/${transcriptionId}`
        eventSource = new EventSource(streamUrl)

        eventSource.addEventListener('open', () => {
          if (isDisposed) return
          setIsConnected(true)
          setError(null)
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
            setProgress(typeof data.progress === 'number' ? data.progress : 0)
            setStage(currentStage)
            setMessage(data.message || '')
            if (data.preview) setPreview(data.preview)
            if (data.eta) setEta(data.eta)
            if (data.model_info) setModelInfo(data.model_info)

            if (currentStage === 'complete' || data.progress === 100) {
              setIsComplete(true)
              setIsFailed(false)
            } else if (currentStage === 'failed') {
              setIsFailed(true)
              setError(data.error || data.message || 'Error en el proceso de transcripción')
            }
          } catch (err) {
            console.warn('Error parsing SSE progress packet:', err)
          }
        })

        eventSource.addEventListener('error', () => {
          if (isDisposed) return
          setIsConnected(false)

          if (eventSource?.readyState === EventSource.CLOSED) {
            if (reconnectAttempts < maxReconnectAttempts) {
              reconnectAttempts++
              const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 15000)
              reconnectTimer = setTimeout(() => {
                if (!isDisposed) connect()
              }, delay)
            } else {
              setError('Conexión con el flujo en tiempo real perdida')
            }
          }

          if (eventSource) {
            eventSource.close()
            eventSource = null
          }
        })
      } catch (err) {
        console.warn('Could not establish EventSource:', err)
        setIsConnected(false)
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
  }, [transcriptionId])

  return {
    progress,
    stage,
    message,
    preview,
    eta,
    modelInfo,
    isComplete,
    isFailed,
    error,
    isConnected,
  }
}
