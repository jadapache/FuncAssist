import { TestBed } from '@angular/core/testing'
import { DEFAULT_TOAST_DURATIONS, ToastService } from './toast.service'

describe('ToastService (parity with React ToastContext)', () => {
  let service: ToastService

  beforeEach(() => {
    TestBed.configureTestingModule({})
    service = TestBed.inject(ToastService)
  })

  it('uses the per-type default durations', () => {
    service.toast.error('boom')
    expect(service.toasts()[0].duration).toBe(DEFAULT_TOAST_DURATIONS.error)
  })

  it('stacks duplicates (same type/title/message) and refreshes the id', () => {
    const first = service.toast.info('hola', 'T')
    const second = service.toast.info('hola', 'T')
    expect(service.toasts().length).toBe(1)
    expect(service.toasts()[0].count).toBe(2)
    expect(second).not.toBe(first)
    expect(service.toasts()[0].id).toBe(second)
  })

  it('keeps at most 3 visible toasts', () => {
    service.toast.info('1')
    service.toast.info('2')
    service.toast.info('3')
    service.toast.info('4')
    expect(service.toasts().map((t) => t.message)).toEqual(['2', '3', '4'])
  })

  it('dismisses by id', () => {
    const id = service.toast.success('ok')
    service.toast.dismiss(id)
    expect(service.toasts().length).toBe(0)
  })
})
