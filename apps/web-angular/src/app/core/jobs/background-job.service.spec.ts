import { TestBed } from '@angular/core/testing'
import { transcriptionApi } from '../../features/transcription/api/transcriptionApi'
import { BackgroundJobService, type BackgroundJobItem } from './background-job.service'

const job = (overrides: Partial<BackgroundJobItem> = {}): BackgroundJobItem => ({
  id: 'trans_1',
  type: 'transcription',
  title: 'Reunión',
  progress: 10,
  status: 'transcribing',
  ...overrides,
})

describe('BackgroundJobService (parity with React BackgroundJobContext)', () => {
  let service: BackgroundJobService

  beforeEach(() => {
    vi.useFakeTimers()
    TestBed.configureTestingModule({})
    service = TestBed.inject(BackgroundJobService)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('merges updates and counts active transcriptions', () => {
    service.addOrUpdateJob(job())
    service.addOrUpdateJob(job({ progress: 50 }))
    expect(service.jobs().length).toBe(1)
    expect(service.jobs()[0].progress).toBe(50)
    expect(service.activeTranscriptionsCount()).toBe(1)
  })

  it('auto-dismisses terminal jobs after 4 s', () => {
    service.addOrUpdateJob(job({ status: 'complete', progress: 100 }))
    vi.advanceTimersByTime(3999)
    expect(service.jobs().length).toBe(1)
    vi.advanceTimersByTime(1)
    expect(service.jobs().length).toBe(0)
  })

  it('does not resurrect a dismissed terminal job', () => {
    service.addOrUpdateJob(job({ status: 'failed' }))
    service.removeJob('trans_1')
    service.addOrUpdateJob(job({ status: 'failed' }))
    expect(service.jobs().length).toBe(0)
  })

  it('cancels a transcription through the API and ignores late non-cancelled updates', async () => {
    const cancel = vi.spyOn(transcriptionApi, 'cancelTranscription').mockResolvedValue(undefined as never)
    service.addOrUpdateJob(job())
    await service.cancelJob('trans_1')
    expect(cancel).toHaveBeenCalledWith('trans_1')
    expect(service.jobs()[0].status).toBe('cancelled')
    service.addOrUpdateJob(job({ progress: 80 }))
    expect(service.jobs()[0].status).toBe('cancelled')
    vi.advanceTimersByTime(3000)
    expect(service.jobs().length).toBe(0)
  })
})
