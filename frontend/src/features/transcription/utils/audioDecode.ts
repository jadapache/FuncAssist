/**
 * Decodes a media file into 16 kHz mono samples for in-browser Whisper.
 *
 * The browser decodes first (any format it supports, up to BROWSER_DECODE_MAX_BYTES). Only when
 * that fails, or the file is larger, the server extracts the audio with FFmpeg, which uploads
 * the whole file.
 */

import { transcriptionApi } from '../api/transcriptionApi'
import { throwIfAborted } from './abort'
import { ASR_SAMPLE_RATE, BROWSER_DECODE_MAX_BYTES } from './audioConstants'
import { parseWav } from './wav'

export interface DecodedAudio {
  samples: Float32Array
  duration: number
}

export interface DecodeOptions {
  signal?: AbortSignal
  onProgress?: (fraction: number, message: string) => void
}

type OfflineContextCtor = typeof OfflineAudioContext

function offlineContextCtor(): OfflineContextCtor {
  const ctor =
    (globalThis as unknown as { OfflineAudioContext?: OfflineContextCtor }).OfflineAudioContext ||
    (globalThis as unknown as { webkitOfflineAudioContext?: OfflineContextCtor }).webkitOfflineAudioContext
  if (!ctor) throw new Error('Web Audio API no está disponible en este navegador.')
  return ctor
}

/** Renders a buffer (any rate, any channels) through a 1-channel 16 kHz context: resample + downmix. */
async function renderToMono16k(buffer: AudioBuffer): Promise<Float32Array> {
  if (buffer.sampleRate === ASR_SAMPLE_RATE) {
    const length = buffer.length
    if (buffer.numberOfChannels === 1) return buffer.getChannelData(0).slice()
    const mono = new Float32Array(length)
    for (let c = 0; c < buffer.numberOfChannels; c++) {
      const data = buffer.getChannelData(c)
      for (let i = 0; i < length; i++) mono[i] += data[i]
    }
    for (let i = 0; i < length; i++) mono[i] /= buffer.numberOfChannels
    return mono
  }
  const Ctor = offlineContextCtor()
  const frames = Math.max(1, Math.ceil(buffer.duration * ASR_SAMPLE_RATE))
  const context = new Ctor(1, frames, ASR_SAMPLE_RATE)
  const source = context.createBufferSource()
  source.buffer = buffer
  source.connect(context.destination)
  source.start(0)
  const rendered = await context.startRendering()
  return rendered.getChannelData(0).slice()
}

async function decodeInBrowser(data: ArrayBuffer): Promise<Float32Array> {
  const Ctor = offlineContextCtor()
  // decodeAudioData resamples to the context rate, so a 16 kHz context returns 16 kHz audio.
  const context = new Ctor(1, 1, ASR_SAMPLE_RATE)
  const decoded = await context.decodeAudioData(data)
  return renderToMono16k(decoded)
}

async function resampleMono(samples: Float32Array, sampleRate: number): Promise<Float32Array> {
  if (sampleRate === ASR_SAMPLE_RATE) return samples
  const Ctor = offlineContextCtor()
  const helper = new Ctor(1, 1, sampleRate)
  const buffer = helper.createBuffer(1, samples.length, sampleRate)
  buffer.getChannelData(0).set(samples)
  return renderToMono16k(buffer)
}

export async function decodeMediaFile(file: File, options: DecodeOptions = {}): Promise<DecodedAudio> {
  const { signal, onProgress } = options
  let browserError = ''

  if (file.size <= BROWSER_DECODE_MAX_BYTES) {
    try {
      onProgress?.(0.05, 'Leyendo archivo…')
      const data = await file.arrayBuffer()
      throwIfAborted(signal)
      onProgress?.(0.3, 'Decodificando audio en el navegador…')
      const samples = await decodeInBrowser(data)
      throwIfAborted(signal)
      onProgress?.(1, 'Audio preparado para transcribir.')
      return { samples, duration: samples.length / ASR_SAMPLE_RATE }
    } catch (err) {
      if (signal?.aborted) throw err
      browserError = err instanceof Error ? err.message : String(err)
    }
  }

  onProgress?.(0.4, 'Extrayendo el audio con FFmpeg en el servidor (se sube el archivo)…')
  try {
    const wav = await transcriptionApi.extractAudioTrack(file, signal)
    throwIfAborted(signal)
    onProgress?.(0.8, 'Preparando audio…')
    const pcm = parseWav(await wav.arrayBuffer())
    const samples = await resampleMono(pcm.samples, pcm.sampleRate)
    onProgress?.(1, 'Audio preparado para transcribir.')
    return { samples, duration: samples.length / ASR_SAMPLE_RATE }
  } catch (serverError) {
    if (signal?.aborted) throw serverError
    const details = [
      browserError ? `navegador: ${browserError.slice(0, 80)}` : '',
      `servidor: ${(serverError instanceof Error ? serverError.message : String(serverError)).slice(0, 120)}`,
    ]
      .filter(Boolean)
      .join('; ')
    throw new Error(
      `No se pudo decodificar "${file.name}". Comprueba que sea un audio o vídeo válido (MP3, WAV, M4A, MP4, OGG, FLAC…). Detalle: ${details}`,
    )
  }
}
