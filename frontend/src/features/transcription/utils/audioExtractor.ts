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
