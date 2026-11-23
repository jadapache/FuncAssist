import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  BrowserLlmError,
  GPU_PRESSURE_KINDS,
  classifyBrowserLlmError,
  isBrowserLlmError,
  toBrowserLlmError,
} from '../errors/browserLlmErrors'
import { LIGHTEST_WEBLLM_MODEL, clearModelUnfit, getUnfitModels, isModelUnfit, markModelUnfit } from '../policies/deviceFit'
import {
  BROWSER_CONTEXT_TOKENS,
  TRIM_MARKER,
  estimatePromptTokens,
  fitPromptToContext,
  outputReserve,
} from '../utils/promptBudget'
import { acquireTabGpuLock, registerGpuConsumer, releaseOtherGpuConsumers } from '../../../core/gpu/gpuResources'
import { copyText, installRandomUUIDPolyfill, randomUUIDFallback } from '../../../core/browser/secureContext'

describe('classifyBrowserLlmError', () => {
  it.each([
    ['WebGPU is not supported in your current environment', 'no_webgpu'],
    ['Unable to find a compatible GPU adapter: navigator.gpu is undefined', 'no_webgpu'],
    ['DXGI_ERROR_DEVICE_HUNG (0x887A0006)', 'gpu_timeout'],
    ['Device was lost. GPU out of memory', 'out_of_memory'],
    ['A valid external Instance reference no longer exists: device lost', 'gpu_lost'],
    ['DXGI_ERROR_DEVICE_REMOVED', 'gpu_lost'],
    ['ContextWindowSizeExceededError: Prompt tokens exceed context window size', 'context_window'],
    ['This model requires WebGPU extension shader-f16, which is not enabled in this browser.', 'unsupported_gpu'],
    ['Network error while fetching shards', 'other'],
  ])('classifies %s', (message, kind) => {
    expect(classifyBrowserLlmError(new Error(message))).toBe(kind)
  })

  it('reports a missing WebGPU on an insecure origin as an HTTPS problem', () => {
    expect(classifyBrowserLlmError(new Error('WebGPU is not supported'), false)).toBe('insecure_context')
  })

  it('does not treat the word "gpu" alone as an out-of-memory error', () => {
    expect(classifyBrowserLlmError(new Error('La GPU respondió bien, pero el servidor devolvió 500'))).toBe('other')
  })

  it('wraps errors keeping the original and a user message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const original = new Error('DXGI_ERROR_DEVICE_HUNG')
    const wrapped = toBrowserLlmError(original, 'Llama-3.2-3B-Instruct-q4f16_1-MLC', 'Llama 3.2 3B')
    expect(isBrowserLlmError(wrapped)).toBe(true)
    expect(wrapped.kind).toBe('gpu_timeout')
    expect(wrapped.original).toBe(original)
    expect(wrapped.message).toContain('Llama 3.2 3B')
    expect(GPU_PRESSURE_KINDS.has(wrapped.kind)).toBe(true)
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })

  it('keeps an already classified error', () => {
    const err = new BrowserLlmError('busy_other_tab', 'otra pestaña')
    expect(toBrowserLlmError(err, null)).toBe(err)
  })
})

describe('fitPromptToContext', () => {
  it('leaves short prompts untouched', () => {
    const messages = [
      { role: 'system' as const, content: 'Eres un asistente.' },
      { role: 'user' as const, content: 'Hola' },
    ]
    const fitted = fitPromptToContext(messages, BROWSER_CONTEXT_TOKENS, 1000)
    expect(fitted.trimmed).toBe(false)
    expect(fitted.messages).toEqual(messages)
    expect(fitted.maxTokens).toBe(1000)
  })

  it('trims the longest message in the middle, keeping its start and end', () => {
    const document = `INICIO ${'palabra '.repeat(5000)} FINAL`
    const fitted = fitPromptToContext(
      [
        { role: 'system', content: 'Instrucciones del sistema.' },
        { role: 'user', content: document },
      ],
      BROWSER_CONTEXT_TOKENS,
      1024,
    )
    expect(fitted.trimmed).toBe(true)
    const content = fitted.messages[1].content
    expect(content.startsWith('INICIO')).toBe(true)
    expect(content.endsWith('FINAL')).toBe(true)
    expect(content).toContain(TRIM_MARKER.trim())
    expect(fitted.messages[0].content).toBe('Instrucciones del sistema.')
    expect(estimatePromptTokens(fitted.messages) + fitted.maxTokens).toBeLessThanOrEqual(BROWSER_CONTEXT_TOKENS)
  })

  it('never reserves more than half the window for the answer', () => {
    expect(outputReserve(4096, 8192)).toBe(2048)
    expect(outputReserve(4096, 10)).toBe(256)
  })
})

describe('deviceFit', () => {
  beforeEach(() => localStorage.clear())

  it('remembers models that did not fit, except the lightest', () => {
    markModelUnfit('Llama-3.2-3B-Instruct-q4f16_1-MLC')
    markModelUnfit(LIGHTEST_WEBLLM_MODEL)
    expect(isModelUnfit('Llama-3.2-3B-Instruct-q4f16_1-MLC')).toBe(true)
    expect(isModelUnfit(LIGHTEST_WEBLLM_MODEL)).toBe(false)
    clearModelUnfit('Llama-3.2-3B-Instruct-q4f16_1-MLC')
    expect(getUnfitModels()).toEqual([])
  })
})

describe('gpuResources', () => {
  it('asks the other consumers to release the GPU', async () => {
    const released: string[] = []
    const offA = registerGpuConsumer('a', () => {
      released.push('a')
    })
    const offB = registerGpuConsumer('b', async () => {
      released.push('b')
    })
    await releaseOtherGpuConsumers('a')
    expect(released).toEqual(['b'])
    offA()
    offB()
  })

  it('does not coordinate tabs when Web Locks are unavailable (plain HTTP)', async () => {
    const release = await acquireTabGpuLock('test-lock')
    expect(typeof release).toBe('function')
  })
})

describe('secure context fallbacks', () => {
  afterEach(() => vi.restoreAllMocks())

  it('generates RFC 4122 v4 ids without crypto.randomUUID', () => {
    const id = randomUUIDFallback()
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(randomUUIDFallback()).not.toBe(id)
  })

  it('installs crypto.randomUUID when the browser hides it', () => {
    const original = crypto.randomUUID
    Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true, writable: true })
    installRandomUUIDPolyfill()
    expect(typeof crypto.randomUUID).toBe('function')
    expect(crypto.randomUUID()).toMatch(/^[0-9a-f-]{36}$/)
    Object.defineProperty(crypto, 'randomUUID', { value: original, configurable: true, writable: true })
  })

  it('copies with execCommand when the Clipboard API is missing', async () => {
    const clipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    const exec = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: exec, configurable: true })
    await expect(copyText('hola')).resolves.toBe(true)
    expect(exec).toHaveBeenCalledWith('copy')
    if (clipboard) Object.defineProperty(navigator, 'clipboard', clipboard)
  })
})
