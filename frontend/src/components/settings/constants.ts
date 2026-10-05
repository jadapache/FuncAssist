import type { BuiltInModel, CloudProvider, RecommendedModel } from './types'

export const BUILT_IN_MODELS: BuiltInModel[] = [
  {
    id: 'gemma3:1b',
    name: 'Gemma 3 1B (Rápido)',
    tag: 'gemma:2b',
    description: 'Modelo ultra rápido. Funciona en cualquier equipo con ~1GB de RAM. Ideal para resúmenes ágiles.',
    size: '~1019 MiB',
    tokens: '32.768 tokens',
  },
  {
    id: 'qwen3.5:4b',
    name: 'Qwen 3.5 4B (Alta Calidad)',
    tag: 'qwen2.5:7b',
    description: 'Modelo Qwen de alta calidad para resúmenes y análisis complejos. Mejor opción Qwen local.',
    size: '~2.6 GiB',
    tokens: '32.768 tokens',
  },
  {
    id: 'qwen3.5:2b',
    name: 'Qwen 3.5 2B (Equilibrado)',
    tag: 'qwen2.5:3b',
    description: 'Modelo Qwen equilibrado para análisis y resúmenes. Alta precisión con requerimientos moderados.',
    size: '~1.2 GiB',
    tokens: '32.768 tokens',
  },
  {
    id: 'deepseek-r1:8b',
    name: 'DeepSeek R1 8B (Razonamiento)',
    tag: 'deepseek-r1:8b',
    description: 'Modelo de razonamiento estructurado (Chain of Thought) para análisis profundo de QA y arquitectura.',
    size: '~4.9 GiB',
    tokens: '65.536 tokens',
  },
  {
    id: 'llama3.2:3b',
    name: 'Llama 3.2 3B (Rápido & Equilibrado)',
    tag: 'llama3.2:3b',
    description: 'Modelo ligero de Meta optimizado para baja latencia y alta precisión en equipos locales.',
    size: '~2.0 GiB',
    tokens: '131.072 tokens',
  },
]

export const BUILT_IN_WHISPER_MODELS = [
  {
    id: 'tiny',
    name: 'Whisper Tiny (Ultra Ligero)',
    tag: 'whisper:tiny',
    description: 'Modelo ultrarrápido con menor consumo de memoria. Ideal para transcripciones rápidas en cualquier equipo.',
    size: '~75 MB',
    accuracy: 'Básica / Rápida',
  },
  {
    id: 'base',
    name: 'Whisper Base (Equilibrado)',
    tag: 'whisper:base',
    description: 'Excelente balance entre velocidad de procesamiento y fidelidad en español.',
    size: '~145 MB',
    accuracy: 'Buena',
  },
  {
    id: 'small',
    name: 'Whisper Small (Recomendado Local)',
    tag: 'whisper:small',
    description: 'Alta fidelidad en reconocimiento de voz, diarización y términos de ingeniería QA.',
    size: '~480 MB',
    accuracy: 'Alta',
  },
  {
    id: 'medium',
    name: 'Whisper Medium (Alta Precisión)',
    tag: 'whisper:medium',
    description: 'Modelo de alta precisión para reuniones extensas con múltiples acentos y ruido ambiental.',
    size: '~1.5 GB',
    accuracy: 'Muy Alta',
  },
]

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
  { id: 'groq', name: 'Groq (API en la Nube)' },
  { id: 'gemini', name: 'Google Gemini (API en la Nube)' },
  { id: 'openai', name: 'OpenAI (API en la Nube)' },
  { id: 'claude', name: 'Claude (Anthropic API en la Nube)' },
]
