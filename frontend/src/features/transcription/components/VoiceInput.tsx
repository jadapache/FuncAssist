import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Square } from 'lucide-react'
import { API_BASE, getAuthHeaders } from '../../../api/client'

export interface VoiceInputProps {
  onTranscriptionReady: (text: string) => void
  disabled?: boolean
  className?: string
}

export const VoiceInput = ({
  onTranscriptionReady,
  disabled = false,
  className = '',
}: VoiceInputProps) => {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const waveformFrameRef = useRef<number | null>(null)
  const [waveform, setWaveform] = useState<number[]>(() => Array.from({ length: 44 }, () => 0.08))

  useEffect(() => {
    return () => {
      stopMediaTracks(streamRef.current)
      if (timerRef.current) clearInterval(timerRef.current)
      if (waveformFrameRef.current) window.cancelAnimationFrame(waveformFrameRef.current)
      analyserRef.current?.disconnect()
      void audioContextRef.current?.close()
    }
  }, [])

  const startRecording = useCallback(async () => {
    setErrorMsg(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMsg('Tu navegador no soporta captura de audio.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []

      const audioContext = new AudioContext()
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 128
      analyser.smoothingTimeConstant = 0.78
      audioContext.createMediaStreamSource(stream).connect(analyser)
      audioContextRef.current = audioContext
      analyserRef.current = analyser
      const samples = new Uint8Array(analyser.fftSize)
      const animateWaveform = () => {
        analyser.getByteTimeDomainData(samples)
        const bars = Array.from({ length: 44 }, (_, index) => {
          const start = Math.floor(index * samples.length / 44)
          const end = Math.max(start + 1, Math.floor((index + 1) * samples.length / 44))
          let peak = 0
          for (let sampleIndex = start; sampleIndex < end; sampleIndex += 1) {
            peak = Math.max(peak, Math.abs(samples[sampleIndex] - 128) / 128)
          }
          return Math.max(0.08, Math.min(1, peak * 2.8))
        })
        setWaveform(bars)
        waveformFrameRef.current = window.requestAnimationFrame(animateWaveform)
      }
      animateWaveform()

      const mimeType = getSupportedMimeType()
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        const audioBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        stopMediaTracks(streamRef.current)
        void uploadAudioSnippet(audioBlob, onTranscriptionReady, setIsTranscribing, setErrorMsg)
      }

      recorder.start(250)
      setIsRecording(true)
      setSeconds(0)
      timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    } catch {
      setErrorMsg('No se pudo acceder al micrófono. Verifica los permisos del navegador.')
    }
  }, [onTranscriptionReady])

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (waveformFrameRef.current) {
      window.cancelAnimationFrame(waveformFrameRef.current)
      waveformFrameRef.current = null
    }
    analyserRef.current?.disconnect()
    analyserRef.current = null
    void audioContextRef.current?.close()
    audioContextRef.current = null
    setWaveform(Array.from({ length: 44 }, () => 0.08))
    setIsRecording(false)
  }, [])

  const formattedTime = formatTimer(seconds)

  if (isTranscribing) {
    return (
      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-50 text-sky-800 text-xs font-medium border border-sky-200 ${className}`}>
        <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" />
        <span>Transcribiendo voz...</span>
      </div>
    )
  }

  if (isRecording) {
    return (
      <div className={`inline-flex items-center gap-2 px-2 py-1 rounded-xl bg-slate-900 text-white text-xs font-medium border border-slate-700 animate-in fade-in duration-150 ${className}`}>
        <span className="font-mono text-[11px] tabular-nums text-slate-200">{formattedTime}</span>
        <div className="flex items-center gap-[2px] h-6 w-44 overflow-hidden" aria-label="Nivel de voz capturada">
          {waveform.map((level, index) => (
            <span
              key={index}
              className="w-[3px] rounded-full bg-sky-300 transition-[height] duration-75"
              style={{ height: `${Math.max(3, level * 22)}px` }}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={stopRecording}
          aria-label="Detener dictado y procesar audio"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-600 text-white hover:bg-rose-700 text-[11px] transition-colors"
        >
          <Square className="h-2.5 w-2.5 fill-white" />
          <span>Detener</span>
        </button>
      </div>
    )
  }

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={startRecording}
        disabled={disabled}
        aria-label="Dictar por voz"
        title="Dictar mensaje por voz"
        className={`p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors disabled:opacity-50 disabled:pointer-events-none ${className}`}
      >
        <Mic className="h-4 w-4" />
      </button>
      {errorMsg && (
        <div className="absolute bottom-full mb-1 left-0 whitespace-nowrap p-1 px-2 text-[10px] bg-rose-100 text-rose-800 border border-rose-300 rounded shadow-xs">
          {errorMsg}
        </div>
      )}
    </div>
  )
}

function stopMediaTracks(stream: MediaStream | null) {
  if (!stream) return
  stream.getTracks().forEach((track) => track.stop())
}

function getSupportedMimeType(): string | undefined {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c
  }
  return undefined
}

function formatTimer(totalSec: number): string {
  const mins = Math.floor(totalSec / 60)
  const secs = totalSec % 60
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

async function uploadAudioSnippet(
  blob: Blob,
  onReady: (text: string) => void,
  setLoading: (v: boolean) => void,
  setError: (msg: string | null) => void,
) {
  setLoading(true)
  try {
    const formData = new FormData()
    formData.append('file', blob, 'dictation.webm')

    const res = await fetch(`${API_BASE}/api/transcription/dictate`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
      body: formData,
    })

    if (!res.ok) throw new Error(`Error en transcripción (${res.status})`)
    const data = (await res.json()) as { text?: string; error?: string }
    if (data.text && data.text.trim()) {
      onReady(data.text.trim())
    } else if (data.error) {
      setError(`Dictado: ${data.error}`)
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Error al enviar audio'
    setError(msg)
  } finally {
    setLoading(false)
  }
}
