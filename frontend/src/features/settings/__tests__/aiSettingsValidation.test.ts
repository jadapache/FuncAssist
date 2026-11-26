import { describe, expect, it } from 'vitest'
import { pickDefaultCloudModel } from '../components/writing/defaultModels'
import { CLOUD_PROVIDERS } from '../constants'
import { validateAiSettingsPayload } from '../validators/settingsValidation'
import type { ModelCatalogItem } from '../types'

const NEW_PROVIDERS = [
  { id: 'openrouter', keyParam: 'openrouterKey' },
  { id: 'deepseek', keyParam: 'deepseekKey' },
] as const

describe('validateAiSettingsPayload for OpenRouter and DeepSeek', () => {
  it.each(NEW_PROVIDERS)('requires an API key for $id when none is saved', ({ id }) => {
    const result = validateAiSettingsPayload({ provider: id, model: 'some-model', isKeyConfigured: false })
    expect(result.isValid).toBe(false)
    expect(result.error).toContain(id.toUpperCase())
  })

  it.each(NEW_PROVIDERS)('accepts a typed key for $id', ({ id, keyParam }) => {
    const result = validateAiSettingsPayload({
      provider: id,
      model: 'some-model',
      isKeyConfigured: false,
      [keyParam]: 'sk-typed',
    })
    expect(result.isValid).toBe(true)
  })

  it.each(NEW_PROVIDERS)('accepts a previously saved key for $id', ({ id }) => {
    const result = validateAiSettingsPayload({ provider: id, model: 'some-model', isKeyConfigured: true })
    expect(result.isValid).toBe(true)
  })

  it('does not accept the key of another provider', () => {
    const result = validateAiSettingsPayload({
      provider: 'deepseek',
      model: 'deepseek-chat',
      isKeyConfigured: false,
      openrouterKey: 'sk-other',
    })
    expect(result.isValid).toBe(false)
  })
})

describe('cloud provider inventory', () => {
  it('lists OpenRouter and DeepSeek', () => {
    const ids = CLOUD_PROVIDERS.map((p) => p.id)
    expect(ids).toEqual(expect.arrayContaining(['openrouter', 'deepseek']))
  })

  it.each([
    ['openrouter', 'meta-llama/llama-3.3-70b-instruct'],
    ['deepseek', 'deepseek-chat'],
  ])('falls back to the preferred default model for %s without a catalog', (provider, expected) => {
    expect(pickDefaultCloudModel(provider, [] as ModelCatalogItem[])).toBe(expected)
  })
})
