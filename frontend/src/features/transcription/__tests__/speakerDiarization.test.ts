import { describe, expect, it } from 'vitest'
import {
  assignSpeakers,
  clusterEmbeddings,
  gatherSamples,
  l2normalize,
  localSpeakers,
  planDiarizationWindows,
  poolEmbedding,
  speakerIdsByAppearance,
} from '../utils/speakerDiarization'

const vec = (...values: number[]) => l2normalize(Float32Array.from(values))

describe('planDiarizationWindows', () => {
  it('splits the audio in 10 s windows', () => {
    expect(planDiarizationWindows(25)).toEqual([
      { start: 0, end: 10 },
      { start: 10, end: 20 },
      { start: 20, end: 25 },
    ])
  })
})

describe('localSpeakers', () => {
  it('keeps single-speaker classes and shifts them by the window offset', () => {
    const speakers = localSpeakers(
      [
        { id: 0, start: 0, end: 1 }, // no speech
        { id: 1, start: 1, end: 3 },
        { id: 4, start: 3, end: 4 }, // overlap of speakers 1 and 2
        { id: 2, start: 4, end: 6 },
        { id: 1, start: 6, end: 7 },
      ],
      3,
      30,
    )
    expect(speakers).toHaveLength(2)
    expect(speakers[0]).toMatchObject({ window: 3, localId: 1, speechSec: 3 })
    expect(speakers[0].spans).toEqual([
      { start: 31, end: 33 },
      { start: 36, end: 37 },
    ])
    expect(speakers[1]).toMatchObject({ localId: 2, speechSec: 2 })
  })
})

describe('gatherSamples', () => {
  it('concatenates the samples of every span', () => {
    const audio = Float32Array.from([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    const out = gatherSamples(audio, 1, [
      { start: 1, end: 3 },
      { start: 7, end: 9 },
    ])
    expect(Array.from(out)).toEqual([1, 2, 7, 8])
  })
})

describe('poolEmbedding', () => {
  it('averages frames and normalises', () => {
    const pooled = poolEmbedding([1, 0, 3, 0], [1, 2, 2])
    expect(pooled[0]).toBeCloseTo(1)
    expect(pooled[1]).toBeCloseTo(0)
  })
})

describe('clusterEmbeddings', () => {
  const voices = [vec(1, 0, 0), vec(0.99, 0.14, 0), vec(0, 1, 0), vec(0.1, 0.99, 0)]

  it('groups similar voices and keeps different ones apart', () => {
    expect(clusterEmbeddings(voices)).toEqual([0, 0, 1, 1])
  })

  it('honours an exact number of speakers', () => {
    expect(clusterEmbeddings(voices, { numSpeakers: 1 })).toEqual([0, 0, 0, 0])
    expect(new Set(clusterEmbeddings(voices, { numSpeakers: 3 })).size).toBe(3)
  })

  it('never returns more than maxSpeakers clusters', () => {
    const labels = clusterEmbeddings([vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)], { maxSpeakers: 2 })
    expect(new Set(labels).size).toBe(2)
  })

  it('handles trivial inputs', () => {
    expect(clusterEmbeddings([])).toEqual([])
    expect(clusterEmbeddings([vec(1, 0)])).toEqual([0])
  })
})

describe('assignSpeakers', () => {
  it('uses overlap, then the nearest turn, then the previous speaker', () => {
    const labels = assignSpeakers(
      [
        { start: 0, end: 2 },
        { start: 2.5, end: 4.5 },
        { start: 10, end: 11 },
        { start: 20, end: 21 },
      ],
      [
        { start: 0, end: 3, label: 5 },
        { start: 3, end: 4.5, label: 7 },
        { start: 11.5, end: 12, label: 7 },
      ],
    )
    expect(labels).toEqual([5, 7, 7, 7])
  })

  it('fills leading segments with the first known speaker', () => {
    expect(assignSpeakers([{ start: 0, end: 1 }, { start: 30, end: 31 }], [{ start: 30, end: 31, label: 2 }])).toEqual([
      2, 2,
    ])
  })
})

describe('speakerIdsByAppearance', () => {
  it('numbers speakers in order of first appearance', () => {
    expect(speakerIdsByAppearance([2, 0, 2, 1])).toEqual(['S1', 'S2', 'S1', 'S3'])
  })
})
