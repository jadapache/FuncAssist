import type { BuiltInModel, CloudProvider, RecommendedModel } from './types'

export const BUILT_IN_MODELS: BuiltInModel[] = [
  {
    id: 'qwen2.5:1.5b',
    name: 'Qwen 2.5 1.5B (Ultra Ligero)',
    tag: 'qwen2.5:1.5b',
    description: 'Modelo ultra rápido y liviano para análisis ágil en cualquier CPU o laptop sin GPU dedicada.',
    size: '~1.0 GiB',
    tokens: '32.768 tokens',
  },
  {
    id: 'qwen2.5:3b',
    name: 'Qwen 2.5 3B (Equilibrado / Recomendado)',
    tag: 'qwen2.5:3b',
    description: 'Modelo insignia equilibrado de alta fidelidad para redacción de historias de usuario y análisis QA.',
    size: '~1.9 GiB',
    tokens: '32.768 tokens',
  },
  {
    id: 'llama3.2:1b',
    name: 'Llama 3.2 1B (Meta Instantáneo)',
    tag: 'llama3.2:1b',
    description: 'Modelo ligero de Meta de última generación, bajo consumo de memoria y respuesta instantánea.',
    size: '~770 MiB',
    tokens: '131.072 tokens',
  },
  {
    id: 'llama3.2:3b',
    name: 'Llama 3.2 3B (Alta Calidad)',
    tag: 'llama3.2:3b',
    description: 'Alta precisión en razonamiento, casos de prueba y análisis estructurado en español e inglés.',
    size: '~2.0 GiB',
    tokens: '131.072 tokens',
  },
  {
    id: 'deepseek-r1:1.5b',
    name: 'DeepSeek R1 1.5B (Razonamiento)',
    tag: 'deepseek-r1:1.5b',
    description: 'Modelo de razonamiento estructurado (Chain-of-Thought) para lógica de validación QA profunda.',
    size: '~1.0 GiB',
    tokens: '65.536 tokens',
  },
  {
    id: 'gemma-2-2b',
    name: 'Gemma 2 2B (Google Open Model)',
    tag: 'gemma-2-2b',
    description: 'Modelo de Google optimizado para seguimiento de instrucciones y redacción técnica concisa.',
    size: '~1.6 GiB',
    tokens: '8.192 tokens',
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
