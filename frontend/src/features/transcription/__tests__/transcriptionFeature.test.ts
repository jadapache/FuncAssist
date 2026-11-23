import { describe, it, expect, beforeEach } from 'vitest'
import {
  generateTranscriptionSlug,
  loadStoredJobRefs,
  saveJobRefs,
  LOCAL_STORAGE_ACTIVE_JOBS,
} from '../utils/transcriptionStorage'
import { condenseTranscriptForBrowser, formatTranscriptForExport, formatTranscriptForPrompt } from '../utils/transcriptFormat'
import { createJob } from '../context/transcriptionJobs'
import type { TranscriptionResult } from '../api/transcriptionApi'

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

  describe('Active job references in localStorage', () => {
    it('stores only id, title, kind and start time of running jobs', () => {
      const running = { ...createJob({ id: 'job_active', kind: 'server', title: 'Kickoff', stage: 'transcribing' }, 1000), progress: 45 }
      const done = createJob({ id: 'job_done', kind: 'server', title: 'Done', stage: 'complete' }, 2000)
      const browser = createJob({ id: 'job_browser', kind: 'browser', title: 'Local', stage: 'transcribing' }, 3000)

      saveJobRefs([running, done, browser])
      const stored = JSON.parse(localStorage.getItem(LOCAL_STORAGE_ACTIVE_JOBS) || '[]')
      expect(stored).toEqual([
        { id: 'job_active', title: 'Kickoff', kind: 'server', startedAt: 1000 },
        { id: 'job_browser', title: 'Local', kind: 'browser', startedAt: 3000 },
      ])
      expect(loadStoredJobRefs().map((ref) => ref.id)).toEqual(['job_active', 'job_browser'])
    })

    it('reads the previous format (progress objects by id), skipping finished jobs', () => {
      localStorage.setItem(
        LOCAL_STORAGE_ACTIVE_JOBS,
        JSON.stringify({
          a: { id: 'a', media_id: 'a', status: 'transcribing', progress: 40, title: 'Uno' },
          b: { id: 'b', media_id: 'b', status: 'complete', progress: 100 },
        }),
      )
      const refs = loadStoredJobRefs()
      expect(refs).toHaveLength(1)
      expect(refs[0]).toMatchObject({ id: 'a', title: 'Uno', kind: 'server' })
    })

    it('clears the key when nothing is running', () => {
      localStorage.setItem(LOCAL_STORAGE_ACTIVE_JOBS, '[]')
      saveJobRefs([])
      expect(localStorage.getItem(LOCAL_STORAGE_ACTIVE_JOBS)).toBeNull()
    })

    it('handles corrupted localStorage gracefully', () => {
      localStorage.setItem(LOCAL_STORAGE_ACTIVE_JOBS, 'invalid json {')
      expect(loadStoredJobRefs()).toEqual([])
    })
  })

  describe('Transcript formatting', () => {
    const record: Pick<TranscriptionResult, 'segments' | 'text' | 'turn_gap_s'> = {
      text: 'Hola. Seguimos.',
      turn_gap_s: 8,
      segments: [
        { id: 's1', start: 0, end: 2, speaker: 'Ana', speaker_id: 'S1', text: 'Hola.', text_raw: 'Eh, hola.' },
        { id: 's2', start: 3, end: 5, speaker: 'Ana', speaker_id: 'S1', text: 'Seguimos.', marked: true },
        { id: 's3', start: 6, end: 8, speaker: 'Luis', speaker_id: 'S2', text: 'De acuerdo.' },
      ],
    }

    it('groups turns for prompts using the clean text', () => {
      expect(formatTranscriptForPrompt(record)).toBe('[00:00] Ana: Hola. Seguimos.\n[00:06] Luis: De acuerdo.')
    })

    it('uses the verbatim text in raw mode', () => {
      expect(formatTranscriptForPrompt(record, 'raw')).toContain('Eh, hola. Seguimos.')
    })

    it('exports one line per segment and highlights marked ones', () => {
      const text = formatTranscriptForExport(record, 'clean', true)
      expect(text.split('\n\n')).toEqual([
        '[00:00] Ana: Hola.',
        '**[IMPORTANTE] [00:03] Ana: Seguimos.**',
        '[00:06] Luis: De acuerdo.',
      ])
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
