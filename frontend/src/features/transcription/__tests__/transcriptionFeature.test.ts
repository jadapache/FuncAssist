import { describe, it, expect, beforeEach } from 'vitest'
import {
  generateTranscriptionSlug,
  loadStoredActiveJobs,
  saveActiveJobsToStorage,
  LOCAL_STORAGE_ACTIVE_JOBS,
} from '../utils/transcriptionStorage'
import { encodeFloat32ToWavBlob } from '../utils/audioExtractor'
import { condenseTranscriptForBrowser } from '../hooks/useTranscriptionActions'
import type { TranscriptionProgress } from '../api/transcriptionApi'

describe('Transcription Feature - Frontend Utilities', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  describe('Slug Generation', () => {
    it('creates URL-friendly slug from title and id prefix', () => {
      const slug = generateTranscriptionSlug('Reunión de Sincronización Q1', '550e8400-e29b-41d4-a716-446655440000')
      expect(slug).toBe('reunion-de-sincronizacion-q1-550e8400')
    })

    it('falls back to default label when title is empty', () => {
      const slug = generateTranscriptionSlug('', 'abc12345-extra')
      expect(slug).toBe('transcripcion-abc12345')
    })

    it('removes special characters and trims excess dashes', () => {
      const slug = generateTranscriptionSlug('¡Proyecto #1 (Final)---v2!', '98765432-xxxx')
      expect(slug).toBe('proyecto-1-final-v2-98765432')
    })
  })

  describe('Active Jobs LocalStorage Persistence', () => {
    it('saves only non-terminal jobs and ignores terminal ones', () => {
      const sampleJobs: Record<string, TranscriptionProgress> = {
        job_active: {
          id: 'job_active',
          media_id: 'media_1',
          status: 'transcribing',
          progress: 45,
          message: 'Transcribiendo...',
        },
        job_done: {
          id: 'job_done',
          media_id: 'media_2',
          status: 'complete',
          progress: 100,
          message: 'Completado',
        },
      }

      saveActiveJobsToStorage(sampleJobs)
      const restored = loadStoredActiveJobs()

      expect(restored.job_active).toBeDefined()
      expect(restored.job_active.status).toBe('transcribing')
      expect(restored.job_done).toBeUndefined()
    })

    it('handles corrupted localStorage gracefully', () => {
      localStorage.setItem(LOCAL_STORAGE_ACTIVE_JOBS, 'invalid json {')
      const result = loadStoredActiveJobs()
      expect(result).toEqual({})
    })
  })

  describe('Audio WAV Encoding', () => {
    it('encodes Float32Array into valid RIFF WAV Blob', async () => {
      const samples = new Float32Array([0.0, 0.5, -0.5, 0.99, -0.99])
      const blob = encodeFloat32ToWavBlob(samples, 16000)

      expect(blob.type).toBe('audio/wav')
      expect(blob.size).toBe(44 + samples.length * 2)

      const buffer = await blob.arrayBuffer()
      const header = new TextDecoder().decode(new Uint8Array(buffer.slice(0, 4)))
      expect(header).toBe('RIFF')
    })
  })

  describe('Transcript Condensation for WebLLM Browser Execution', () => {
    it('returns unmodified transcript when within character budget', () => {
      const shortText = '[00:00] Participante: Hola\n[00:10] Participante: Fin'
      expect(condenseTranscriptForBrowser(shortText, 500)).toBe(shortText)
    })

    it('condenses long transcripts and includes timeline representation', () => {
      const lines = Array.from({ length: 60 }, (_, i) => `[0${Math.floor(i / 10)}:${(i % 10) * 6}] Juan: Debate punto ${i}`)
      const longTranscript = lines.join('\n')
      const condensed = condenseTranscriptForBrowser(longTranscript, 300)

      expect(condensed.length).toBeLessThan(longTranscript.length)
      expect(condensed).toContain('Juan')
      expect(condensed).toContain('...')
    })
  })
})
