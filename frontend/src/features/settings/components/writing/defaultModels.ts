import type { ModelCatalogItem } from '../../../../api/client'

// Preferred defaults, used only when present in the synced catalog: hardcoded names get retired
// by providers (e.g. llama-3.1-8b-instant, claude-3-5-*-latest), the catalog reflects what exists.
const PREFERRED_DEFAULT_MODELS: Record<string, string[]> = {
  groq: ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile'],
  gemini: ['gemini-2.5-flash'],
  openai: ['gpt-4o-mini', 'gpt-4o'],
  claude: ['claude-sonnet-4-5', 'claude-haiku-4-5'],
}

/** Default chat model for a cloud provider: a preferred one if the catalog has it, else the first available. */
export function pickDefaultCloudModel(provider: string, catalog: ModelCatalogItem[]): string {
  const ids = catalog
    .filter((m) => m.provider === provider && m.task_type === 'chat_writing')
    .map((m) => m.raw_id || m.id)
  const preferred = PREFERRED_DEFAULT_MODELS[provider] ?? []
  return preferred.find((id) => ids.includes(id)) ?? ids[0] ?? preferred[0] ?? ''
}
