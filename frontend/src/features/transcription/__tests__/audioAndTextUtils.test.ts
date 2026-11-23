import { describe, expect, it } from 'vitest'
import { parseWav } from '../utils/wav'
import { buildCompactAudio, detectSpeechRegions, remapTime } from '../utils/vad'
import { planWindows, segmentsFromWindow } from '../utils/windowMerge'
import { estimateRemainingSeconds } from '../utils/etaCalculator'
import {
  BROWSER_STAGE_RANGES,
  SERVER_STAGE_RANGES,
  getStageText,
  isStreamFinished,
  normalizeStage,
  overallProgress,
} from '../utils/transcriptionStages'
import { groupTurns } from '../utils/turns'
import { listSpeakers } from '../utils/speakers'
import { formatDuration, formatEtaSeconds, formatProgressEta, formatTimestamp } from '../utils/time'
import type { TranscriptionSegment } from '../api/transcriptionApi'

// ---------------------------------------------------------------------------- WAV

interface WavSpec {
  format: number
  bits: number
  sampleRate?: number
  /** Interleaved raw sample values as they must be written. */
  frames: number[][]
  extensibleSubformat?: number
  extraChunk?: { id: string; size: number }
}

function buildWav(spec: WavSpec): ArrayBuffer {
  const channels = spec.frames[0]?.length ?? 1
  const bytes = spec.bits / 8
  const dataSize = spec.frames.length * channels * bytes
  const fmtSize = spec.extensibleSubformat !== undefined ? 40 : 16
  const extra = spec.extraChunk ? 8 + spec.extraChunk.size + (spec.extraChunk.size % 2) : 0
  const buffer = new ArrayBuffer(12 + 8 + fmtSize + extra + 8 + dataSize)
  const view = new DataView(buffer)
  const ascii = (offset: number, text: string) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)))

  ascii(0, 'RIFF')
  view.setUint32(4, buffer.byteLength - 8, true)
  ascii(8, 'WAVE')
  ascii(12, 'fmt ')
  view.setUint32(16, fmtSize, true)
  view.setUint16(20, spec.extensibleSubformat !== undefined ? 0xfffe : spec.format, true)
  view.setUint16(22, channels, true)
  view.setUint32(24, spec.sampleRate ?? 16000, true)
  view.setUint32(28, (spec.sampleRate ?? 16000) * channels * bytes, true)
  view.setUint16(32, channels * bytes, true)
  view.setUint16(34, spec.bits, true)
  let offset = 36
  if (spec.extensibleSubformat !== undefined) {
    view.setUint16(36, 22, true)
    view.setUint16(38, spec.bits, true)
    view.setUint32(40, 0, true)
    view.setUint16(44, spec.extensibleSubformat, true)
    offset = 12 + 8 + fmtSize
  }
  if (spec.extraChunk) {
    ascii(offset, spec.extraChunk.id)
    view.setUint32(offset + 4, spec.extraChunk.size, true)
    offset += extra
  }
  ascii(offset, 'data')
  view.setUint32(offset + 4, dataSize, true)
  offset += 8
  for (const frame of spec.frames) {
    for (const value of frame) {
      if (spec.format === 3 && spec.bits === 32) view.setFloat32(offset, value, true)
      else if (spec.bits === 8) view.setUint8(offset, value)
      else if (spec.bits === 16) view.setInt16(offset, value, true)
      else if (spec.bits === 24) {
        const v = value < 0 ? value + 0x1000000 : value
        view.setUint8(offset, v & 0xff)
        view.setUint8(offset + 1, (v >> 8) & 0xff)
        view.setUint8(offset + 2, (v >> 16) & 0xff)
      } else if (spec.bits === 32) view.setInt32(offset, value, true)
      offset += bytes
    }
  }
  return buffer
}

describe('parseWav', () => {
  it('averages 16-bit stereo into mono', () => {
    const pcm = parseWav(buildWav({ format: 1, bits: 16, frames: [[16384, -16384], [16384, 16384]] }))
    expect(Array.from(pcm.samples)).toEqual([0, 0.5])
    expect(pcm.sampleRate).toBe(16000)
    expect(pcm.duration).toBeCloseTo(2 / 16000)
  })

  it('reads 24-bit samples including negative values', () => {
    const pcm = parseWav(buildWav({ format: 1, bits: 24, frames: [[4194304], [-4194304]] }))
    expect(pcm.samples[0]).toBeCloseTo(0.5)
    expect(pcm.samples[1]).toBeCloseTo(-0.5)
  })

  it('reads 8-bit unsigned and 32-bit float samples', () => {
    expect(Array.from(parseWav(buildWav({ format: 1, bits: 8, frames: [[192], [64]] })).samples)).toEqual([0.5, -0.5])
    const float = parseWav(buildWav({ format: 3, bits: 32, frames: [[0.25], [-1]] }))
    expect(Array.from(float.samples)).toEqual([0.25, -1])
  })

  it('supports WAVE_FORMAT_EXTENSIBLE and skips other chunks', () => {
    const pcm = parseWav(
      buildWav({ format: 3, bits: 32, frames: [[0.5]], extensibleSubformat: 3, extraChunk: { id: 'LIST', size: 3 } }),
    )
    expect(Array.from(pcm.samples)).toEqual([0.5])
  })

  it('rejects files that are not WAV', () => {
    expect(() => parseWav(new ArrayBuffer(16))).toThrow()
  })
})

// ---------------------------------------------------------------------------- VAD

const RATE = 16000

function signal(parts: Array<{ seconds: number; amplitude: number }>): Float32Array {
  const total = parts.reduce((sum, part) => sum + Math.round(part.seconds * RATE), 0)
  const samples = new Float32Array(total)
  let offset = 0
  for (const part of parts) {
    const count = Math.round(part.seconds * RATE)
    for (let i = 0; i < count; i++) samples[offset + i] = part.amplitude * Math.sin((2 * Math.PI * 220 * i) / RATE)
    offset += count
  }
  return samples
}

describe('voice activity detection', () => {
  it('cuts long silences keeping a margin around speech', () => {
    const samples = signal([
      { seconds: 1, amplitude: 0.5 },
      { seconds: 4, amplitude: 0 },
      { seconds: 1, amplitude: 0.5 },
    ])
    const regions = detectSpeechRegions(samples, RATE)
    expect(regions).toHaveLength(2)
    expect(regions[0].start).toBe(0)
    expect(regions[0].end).toBeCloseTo(1.3, 1)
    expect(regions[1].start).toBeCloseTo(4.7, 1)
    expect(regions[1].end).toBeCloseTo(6, 3)

    const { audio, timeMap } = buildCompactAudio(samples, RATE, regions)
    const firstLength = timeMap[0].duration
    expect(audio.length / RATE).toBeCloseTo(firstLength + timeMap[1].duration, 3)
    // A time in the second region maps back past the removed silence.
    expect(remapTime(firstLength + 0.5, timeMap)).toBeCloseTo(regions[1].start + 0.5, 2)
    // The joint maps to the start of the next region, or to the end of the previous one for segment ends.
    expect(remapTime(firstLength, timeMap)).toBeCloseTo(regions[1].start, 2)
    expect(remapTime(firstLength, timeMap, true)).toBeCloseTo(regions[0].end, 2)
  })

  it('keeps short pauses and returns the original audio untouched', () => {
    const samples = signal([
      { seconds: 1, amplitude: 0.5 },
      { seconds: 1, amplitude: 0 },
      { seconds: 1, amplitude: 0.5 },
    ])
    const regions = detectSpeechRegions(samples, RATE)
    expect(regions).toEqual([{ start: 0, end: 3 }])
    expect(buildCompactAudio(samples, RATE, regions).audio).toBe(samples)
  })

  it('returns no regions for silent audio', () => {
    expect(detectSpeechRegions(new Float32Array(RATE * 3), RATE)).toEqual([])
  })
})

// ---------------------------------------------------------------------------- Windows

describe('overlapping Whisper windows', () => {
  it('plans 30 s windows every 25 s with owned spans meeting in the middle of each overlap', () => {
    const windows = planWindows(70)
    expect(windows.map((w) => [w.start, w.end])).toEqual([
      [0, 30],
      [25, 55],
      [50, 70],
    ])
    expect(windows.map((w) => [w.ownStart, w.ownEnd])).toEqual([
      [0, 27.5],
      [27.5, 52.5],
      [52.5, 70],
    ])
    expect(windows[2].isLast).toBe(true)
    expect(planWindows(20)).toHaveLength(1)
    expect(planWindows(0)).toEqual([])
  })

  it('keeps only the segments whose midpoint the window owns', () => {
    const [, second] = planWindows(70)
    const segments = segmentsFromWindow(second, [
      { text: ' cortado ', timestamp: [0, 2] },
      { text: 'propio', timestamp: [3, 6] },
      { text: 'siguiente', timestamp: [27, null] },
    ])
    expect(segments).toEqual([{ start: 28, end: 31, text: 'propio' }])
  })

  it('falls back to the whole window text without timestamps', () => {
    const [only] = planWindows(12)
    expect(segmentsFromWindow(only, [], ' hola ')).toEqual([{ start: 0, end: 12, text: 'hola' }])
  })
})

// ---------------------------------------------------------------------------- Progress texts, ETA, time

describe('progress helpers', () => {
  it('estimates the remaining time from measured throughput', () => {
    expect(estimateRemainingSeconds(30, 120, 10)).toBeCloseTo(30)
    expect(estimateRemainingSeconds(0, 120, 10)).toBeNull()
    expect(estimateRemainingSeconds(30, 120, 0.2)).toBeNull()
    expect(estimateRemainingSeconds(120, 120, 10)).toBe(0)
  })

  it('maps stage progress into the overall range', () => {
    expect(overallProgress('transcribing', 0.5, SERVER_STAGE_RANGES)).toBe(50)
    expect(overallProgress('uploading', 1, SERVER_STAGE_RANGES)).toBe(10)
    expect(overallProgress('model_download', 0.5, BROWSER_STAGE_RANGES)).toBe(15)
    expect(overallProgress('cleaning', 2, SERVER_STAGE_RANGES)).toBe(85)
  })

  it('keeps the stream open while the summary of a complete job runs', () => {
    expect(isStreamFinished({ stage: 'complete', summary_status: 'running' })).toBe(false)
    expect(isStreamFinished({ stage: 'complete', summary_status: 'done' })).toBe(true)
    expect(isStreamFinished({ stage: 'failed' })).toBe(true)
    expect(isStreamFinished({ stage: 'transcribing' })).toBe(false)
  })

  it('describes each stage, showing the real error on failure', () => {
    expect(getStageText({ stage: 'failed', error: 'Clave de API inválida' })).toBe('Clave de API inválida')
    expect(getStageText({ stage: 'queued', queue_position: 2 })).toBe('En cola (posición 2)')
    expect(getStageText({ stage: 'transcribing', chunks_done: 2, chunks_total: 7 })).toBe('Transcribiendo fragmento 3 de 7…')
    expect(getStageText({ stage: 'cleaning' })).toBe('Limpiando texto…')
    expect(normalizeStage('summarizing')).toBe('saving')
    expect(normalizeStage('algo-raro')).toBe('transcribing')
  })

  it('formats times and ETAs', () => {
    expect(formatTimestamp(65)).toBe('01:05')
    expect(formatTimestamp(3725)).toBe('1:02:05')
    expect(formatDuration(3900)).toBe('1 h 05 min')
    expect(formatDuration(750)).toBe('12 min 30 s')
    expect(formatDuration(45)).toBe('45 s')
    expect(formatEtaSeconds(90)).toBe('~1 min 30 s')
    expect(formatEtaSeconds(null)).toBe('')
    expect(formatProgressEta({ eta_seconds: null, eta: '~2 min' })).toBe('~2 min')
    expect(formatProgressEta({ eta_seconds: 30 })).toBe('~30 s')
  })
})

// ---------------------------------------------------------------------------- Turns and speakers

const seg = (id: string, start: number, end: number, speakerId: string, text: string, extra: Partial<TranscriptionSegment> = {}) => ({
  id,
  start,
  end,
  speaker_id: speakerId,
  speaker: speakerId === 'S1' ? 'Ana' : 'Luis',
  text,
  ...extra,
})

describe('turn grouping', () => {
  it('joins consecutive segments of the same speaker and splits on speaker change or long pauses', () => {
    const turns = groupTurns([
      seg('1', 0, 2, 'S1', 'Hola.'),
      seg('2', 6, 8, 'S1', 'Sigo yo tras una pausa.'),
      seg('3', 20, 22, 'S1', 'Después de una pausa larga.'),
      seg('4', 22.5, 24, 'S2', 'Respondo.'),
    ])
    expect(turns.map((turn) => turn.items.map((item) => item.segment.id))).toEqual([['1', '2'], ['3'], ['4']])
    expect(turns[0]).toMatchObject({ speakerKey: 'S1', start: 0, end: 8 })
  })

  it('limits the size of a turn and skips empty segments', () => {
    const long = 'x'.repeat(400)
    const turns = groupTurns([seg('1', 0, 1, 'S1', long), seg('2', 1, 2, 'S1', '   '), seg('3', 2, 3, 'S1', long)])
    expect(turns).toHaveLength(2)
  })

  it('uses the verbatim text in raw mode', () => {
    const [turn] = groupTurns([seg('1', 0, 1, 'S1', 'Hola.', { text_raw: 'Eh, hola.' })], { mode: 'raw' })
    expect(turn.items[0].text).toBe('Eh, hola.')
  })
})

describe('listSpeakers', () => {
  it('uses the speakers map and keeps colors by index', () => {
    const speakers = listSpeakers({
      speakers: { S1: { name: 'Ana', color_index: 3 }, S2: { name: 'Luis', color_index: 0 }, S3: { name: 'Nueva', color_index: 2 } },
      segments: [seg('1', 0, 1, 'S2', 'a'), seg('2', 1, 2, 'S1', 'b'), seg('3', 2, 3, 'S2', 'c')],
    })
    expect(speakers).toEqual([
      { id: 'S2', name: 'Luis', colorIndex: 0, segmentCount: 2 },
      { id: 'S1', name: 'Ana', colorIndex: 3, segmentCount: 1 },
      { id: 'S3', name: 'Nueva', colorIndex: 2, segmentCount: 0 },
    ])
  })

  it('derives speakers from names for records without a map', () => {
    const speakers = listSpeakers({
      segments: [
        { start: 0, end: 1, speaker: 'Participante 1', text: 'a' },
        { start: 1, end: 2, speaker: 'Participante 2', text: 'b' },
      ],
    })
    expect(speakers.map((s) => [s.id, s.colorIndex])).toEqual([
      ['Participante 1', 0],
      ['Participante 2', 1],
    ])
  })
})
