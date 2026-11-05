/**
 * Browser-native audio extraction and resampling to 16 kHz mono Float32Array.
 * Processes video and audio files entirely in client memory without uploading bytes.
 */

export interface ExtractedAudioData {
  audioData: Float32Array
  sampleRate: number
  duration: number
}

/**
 * Extracts and downsamples audio from any supported media file (video or audio)
 * to 16,000 Hz single-channel PCM Float32Array required by Whisper.
 */
export async function extractAudioTrackFromMedia(
  file: File,
  targetSampleRate = 16000,
  onProgress?: (progressPct: number, message: string) => void
): Promise<ExtractedAudioData> {
  onProgress?.(2, 'Leyendo archivo multimedia en memoria...')

  const arrayBuffer = await file.arrayBuffer()
  onProgress?.(5, 'Decodificando pistas de audio en el navegador...')

  // Standard AudioContext to decode container audio (AAC, MP3, Opus, PCM, etc.)
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) {
    throw new Error('Web Audio API no está soportada en este navegador.')
  }

  const tempContext = new AudioCtx()
  let decodedBuffer: AudioBuffer
  try {
    decodedBuffer = await tempContext.decodeAudioData(arrayBuffer)
  } catch (err: unknown) {
    const isVideo =
      file.type.startsWith('video/') ||
      /\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v)$/i.test(file.name)
    if (isVideo) {
      throw new Error(
        `El decodificador del navegador no puede procesar el contenedor de video '${file.name}' localmente. ` +
        `Usa un archivo de audio (MP3, WAV, M4A, OGG, FLAC) o configura Groq Whisper Cloud en Ajustes para procesar video.`
      )
    }
    throw new Error(
      `No se pudo decodificar el audio en el navegador: ${err instanceof Error ? err.message : String(err)}`
    )
  } finally {
    void tempContext.close()
  }

  onProgress?.(8, 'Normalizando y remuestreando a 16 kHz mono...')

  const totalLength = Math.ceil(decodedBuffer.duration * targetSampleRate)
  const offlineCtx = new OfflineAudioContext(1, totalLength, targetSampleRate)

  const source = offlineCtx.createBufferSource()
  source.buffer = decodedBuffer
  source.connect(offlineCtx.destination)
  source.start(0)

  const resampledBuffer = await offlineCtx.startRendering()
  const monoChannel = resampledBuffer.getChannelData(0)

  onProgress?.(10, 'Audio preparado para transcripción.')

  return {
    audioData: monoChannel,
    sampleRate: targetSampleRate,
    duration: decodedBuffer.duration,
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
