/**
 * Client-side audio processing for Web App.
 * Uses Web Audio API for fast browser-side decoding when possible (< 30 MB),
 * and delegates to the server FFmpeg endpoint for larger or unsupported formats.
 */

import { transcriptionApi } from '../api/transcriptionApi'

export interface ExtractedAudioData {
  audioData: Float32Array
  sampleRate: number
  duration: number
}

function downmixToMono(buffer: AudioBuffer): Float32Array {
  if (buffer.numberOfChannels === 1) {
    return buffer.getChannelData(0).slice()
  }
  const length = buffer.length
  const mono = new Float32Array(length)
  const channels = buffer.numberOfChannels
  for (let c = 0; c < channels; c++) {
    const chData = buffer.getChannelData(c)
    for (let i = 0; i < length; i++) {
      mono[i] += chData[i] / channels
    }
  }
  return mono
}

async function decodeWithAudioContext(arrayBuffer: ArrayBuffer): Promise<AudioBuffer> {
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) {
    throw new Error('Web Audio API no esta soportada en este navegador.')
  }
  const tempContext = new AudioCtx()
  try {
    return await tempContext.decodeAudioData(arrayBuffer)
  } finally {
    void tempContext.close()
  }
}

function parseWavPcmToFloat32(arrayBuffer: ArrayBuffer): {
  audioData: Float32Array
  sampleRate: number
  duration: number
} {
  const view = new DataView(arrayBuffer)
  let offset = 12
  let sampleRate = 16000
  let channels = 1
  let bitsPerSample = 16

  while (offset < view.byteLength - 8) {
    const chunkId = String.fromCharCode(
      view.getUint8(offset),
      view.getUint8(offset + 1),
      view.getUint8(offset + 2),
      view.getUint8(offset + 3)
    )
    const chunkSize = view.getUint32(offset + 4, true)
    if (chunkId === 'fmt ') {
      channels = view.getUint16(offset + 10, true)
      sampleRate = view.getUint32(offset + 12, true)
      bitsPerSample = view.getUint16(offset + 22, true)
      offset += 8 + chunkSize
    } else if (chunkId === 'data') {
      const dataOffset = offset + 8
      const bytesPerSample = bitsPerSample / 8
      const totalSamples = Math.floor(chunkSize / bytesPerSample / channels)
      const float32 = new Float32Array(totalSamples)

      if (bitsPerSample === 16) {
        for (let i = 0; i < totalSamples; i++) {
          const bytePos = dataOffset + i * 2 * channels
          if (bytePos + 1 < view.byteLength) {
            float32[i] = view.getInt16(bytePos, true) / 32768.0
          }
        }
      }
      const duration = totalSamples / sampleRate
      return { audioData: float32, sampleRate, duration }
    } else {
      offset += 8 + chunkSize
    }
  }

  throw new Error('Estructura WAV no contiene bloque PCM valido.')
}

async function resampleAudio(
  audioData: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number
): Promise<Float32Array> {
  if (sourceSampleRate === targetSampleRate) {
    return audioData
  }

  const totalLength = Math.ceil(audioData.length * (targetSampleRate / sourceSampleRate))
  const offlineCtx = new OfflineAudioContext(1, totalLength, targetSampleRate)

  const audioBuffer = offlineCtx.createBuffer(1, audioData.length, sourceSampleRate)
  audioBuffer.getChannelData(0).set(audioData)

  const source = offlineCtx.createBufferSource()
  source.buffer = audioBuffer
  source.connect(offlineCtx.destination)
  source.start(0)

  const resampledBuffer = await offlineCtx.startRendering()
  return resampledBuffer.getChannelData(0)
}

export async function extractAudioTrackFromMedia(
  file: File,
  targetSampleRate = 16000,
  onProgress?: (progressPct: number, message: string) => void
): Promise<ExtractedAudioData> {
  let audioData: Float32Array = new Float32Array(0)
  let sampleRate: number = targetSampleRate
  let duration: number = 0
  let decodedSuccessfully = false
  let webAudioError = ''

  if (file.size < 30 * 1024 * 1024) {
    onProgress?.(4, 'Decodificando audio en el navegador (Web Audio API)...')
    try {
      const buffer = await file.arrayBuffer()
      const audioBuffer = await decodeWithAudioContext(buffer)
      audioData = downmixToMono(audioBuffer)
      sampleRate = audioBuffer.sampleRate
      duration = audioBuffer.duration
      decodedSuccessfully = true
    } catch (err) {
      webAudioError = String(err)
    }
  }

  if (!decodedSuccessfully) {
    onProgress?.(6, 'Extrayendo audio con motor FFmpeg del servidor...')
    try {
      const wavBlob = await transcriptionApi.extractAudioTrack(file)
      const wavBuffer = await wavBlob.arrayBuffer()
      const pcmResult = parseWavPcmToFloat32(wavBuffer)
      audioData = pcmResult.audioData
      sampleRate = pcmResult.sampleRate
      duration = pcmResult.duration
      decodedSuccessfully = true
    } catch (serverError) {
      const details = [
        webAudioError ? `Web Audio API: ${webAudioError.substring(0, 60)}` : '',
        `Servidor FFmpeg: ${String(serverError).substring(0, 80)}`,
      ].filter(Boolean).join('; ')

      throw new Error(
        `No se pudo decodificar el archivo de audio "${file.name}". ` +
        `Verifica que es un formato valido (MP3, WAV, FLAC, AAC/M4A, OGG). ` +
        `Detalles: ${details}`
      )
    }
  }

  if (sampleRate !== targetSampleRate) {
    onProgress?.(8, `Remuestreando de ${sampleRate} Hz a ${targetSampleRate} Hz...`)
    audioData = await resampleAudio(audioData, sampleRate, targetSampleRate)
  }

  onProgress?.(10, 'Audio preparado para transcripcion.')

  return {
    audioData,
    sampleRate: targetSampleRate,
    duration,
  }
}

function writeAsciiString(view: DataView, offset: number, text: string): void {
  for (let i = 0; i < text.length; i++) {
    view.setUint8(offset + i, text.charCodeAt(i))
  }
}

function writeFloatTo16BitPcm(view: DataView, offset: number, samples: Float32Array): void {
  let byteOffset = offset
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    const intSample = s < 0 ? s * 0x8000 : s * 0x7fff
    view.setInt16(byteOffset, intSample, true)
    byteOffset += 2
  }
}

export function encodeFloat32ToWavBlob(samples: Float32Array, sampleRate = 16000): Blob {
  const dataSize = samples.length * 2
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  writeAsciiString(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeAsciiString(view, 8, 'WAVE')

  writeAsciiString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)

  writeAsciiString(view, 36, 'data')
  view.setUint32(40, dataSize, true)
  writeFloatTo16BitPcm(view, 44, samples)

  return new Blob([buffer], { type: 'audio/wav' })
}
