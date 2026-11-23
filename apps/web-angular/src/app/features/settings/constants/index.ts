import type { BuiltInModel, CloudProvider, RecommendedModel } from '../types'

// Catálogo de modelos built-in 
export const BUILT_IN_MODELS: BuiltInModel[] = []


// Catálogo de modelos Whisper built-in 
export const BUILT_IN_WHISPER_MODELS: Array<{
  id: string
  name: string
  tag: string
  description: string
  size: string
  accuracy: string
}> = []


export const OLLAMA_RECOMMENDED: RecommendedModel[] = [
  { id: 'gemma3:1b', name: 'Gemma 3 1B (Recomendado, ~800MB)' },
  { id: 'llama3.2', name: 'Llama 3.2 3B (Ultra Rápido)' },
  { id: 'qwen2.5:3b', name: 'Qwen 2.5 3B (Equilibrado)' },
  { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B (Alta Calidad)' },
  { id: 'deepseek-r1:8b', name: 'DeepSeek R1 8B (Razonamiento)' },
  { id: 'mistral', name: 'Mistral 7B (Propósito General)' },
  { id: 'phi4', name: 'Phi-4 14B (Lógica y Código)' },
]

export const CLOUD_PROVIDERS: CloudProvider[] = [
  { id: 'groq', name: 'Groq' },
  { id: 'gemini', name: 'Google' },
  { id: 'openai', name: 'OpenAI' },
  { id: 'claude', name: 'Anthropic' },
]
