export interface DecodedPcm {
  /** Mono samples in [-1, 1] (all channels averaged). */
  samples: Float32Array
  sampleRate: number
  duration: number
}

const FORMAT_PCM = 1
const FORMAT_FLOAT = 3
const FORMAT_EXTENSIBLE = 0xfffe

function chunkId(view: DataView, offset: number): string {
  return String.fromCharCode(
    view.getUint8(offset),
    view.getUint8(offset + 1),
    view.getUint8(offset + 2),
    view.getUint8(offset + 3),
  )
}

type SampleReader = (view: DataView, offset: number) => number

function sampleReader(format: number, bits: number): SampleReader {
  if (format === FORMAT_FLOAT) {
    if (bits === 32) return (v, o) => v.getFloat32(o, true)
    if (bits === 64) return (v, o) => v.getFloat64(o, true)
  }
  if (format === FORMAT_PCM) {
    if (bits === 8) return (v, o) => (v.getUint8(o) - 128) / 128
    if (bits === 16) return (v, o) => v.getInt16(o, true) / 32768
    if (bits === 24)
      return (v, o) => {
        const value = v.getUint8(o) | (v.getUint8(o + 1) << 8) | (v.getUint8(o + 2) << 16)
        return (value & 0x800000 ? value - 0x1000000 : value) / 8388608
      }
    if (bits === 32) return (v, o) => v.getInt32(o, true) / 2147483648
  }
  throw new Error(`Formato WAV no soportado (formato ${format}, ${bits} bits).`)
}

/**
 * Parses a RIFF/WAVE file: PCM 8/16/24/32-bit, IEEE float 32/64-bit and WAVE_FORMAT_EXTENSIBLE.
 * Channels are averaged into mono.
 */
export function parseWav(buffer: ArrayBuffer): DecodedPcm {
  const view = new DataView(buffer)
  if (view.byteLength < 12 || chunkId(view, 0) !== 'RIFF' || chunkId(view, 8) !== 'WAVE') {
    throw new Error('El archivo no es un WAV válido.')
  }

  let format = 0
  let channels = 0
  let sampleRate = 0
  let bits = 0
  let offset = 12

  while (offset + 8 <= view.byteLength) {
    const id = chunkId(view, offset)
    const size = view.getUint32(offset + 4, true)
    const body = offset + 8

    if (id === 'fmt ') {
      format = view.getUint16(body, true)
      channels = view.getUint16(body + 2, true)
      sampleRate = view.getUint32(body + 4, true)
      bits = view.getUint16(body + 14, true)
      if (format === FORMAT_EXTENSIBLE && size >= 26) {
        // The sub-format GUID starts with the actual format code.
        format = view.getUint16(body + 24, true)
      }
    } else if (id === 'data') {
      if (!format || !channels || !sampleRate || !bits) {
        throw new Error('El WAV no declara el formato antes de los datos.')
      }
      const read = sampleReader(format, bits)
      const bytesPerSample = bits / 8
      const frameBytes = bytesPerSample * channels
      // Streamed WAVs may declare 0 or 0xFFFFFFFF as size: use what is actually there.
      const available = view.byteLength - body
      const dataBytes = size > 0 && size <= available ? size : available
      const frames = Math.floor(dataBytes / frameBytes)
      const samples = new Float32Array(frames)
      for (let i = 0; i < frames; i++) {
        const frameOffset = body + i * frameBytes
        let sum = 0
        for (let c = 0; c < channels; c++) {
          sum += read(view, frameOffset + c * bytesPerSample)
        }
        samples[i] = sum / channels
      }
      return { samples, sampleRate, duration: frames / sampleRate }
    }
    // Chunks are padded to an even size.
    offset = body + size + (size % 2)
  }

  throw new Error('El WAV no contiene datos de audio.')
}
