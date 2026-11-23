/**
 * Remembers, per browser, which in-browser models did not fit this device's GPU, so the next
 * request goes straight to a lighter model and Settings can warn about it. Browser storage is a
 * per-device convenience: when it is unavailable everything still works without the memory.
 */

const STORAGE_KEY = 'funcassist.webllm.unfitModels'
/** Lightest catalog model (~0.9 GB of VRAM with a 4,096-token context). */
export const LIGHTEST_WEBLLM_MODEL = 'Llama-3.2-1B-Instruct-q4f16_1-MLC'

function read(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : []
  } catch {
    return []
  }
}

export function getUnfitModels(): string[] {
  return read()
}

export function isModelUnfit(modelId: string): boolean {
  return read().includes(modelId)
}

export function markModelUnfit(modelId: string): void {
  if (!modelId || modelId === LIGHTEST_WEBLLM_MODEL) return
  try {
    const current = read()
    if (!current.includes(modelId)) localStorage.setItem(STORAGE_KEY, JSON.stringify([...current, modelId]))
  } catch {
    // No storage (private mode, blocked site data): the fallback still happens, it is just not remembered.
  }
}

/** Called when the user explicitly selects or downloads a model: give it another chance. */
export function clearModelUnfit(modelId: string): void {
  try {
    const remaining = read().filter((id) => id !== modelId)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(remaining))
  } catch {
    // ignore
  }
}
