import type { WebLLMModelDefinition } from '../types/webLlm'
import type { ModelCatalogItem } from '../../../api/client'

export interface ClientAsrModelDefinition {
  id: string
  name: string
  description: string
  downloadSize: string
  badge: string
  accuracy: string
  tier: 'speed' | 'balanced' | 'quality'
}

export const CLIENT_WEBLLM_MODELS: readonly WebLLMModelDefinition[] = [
  {
    id: 'Llama-3.2-1B-Instruct-q4f16_1-MLC',
    name: 'Llama 3.2 1B (Ligero)',
    tag: 'llama-3.2-1b',
    description: 'Modelo ultraligero de Meta, óptimo para equipos con memoria gráfica ajustada.',
    downloadSize: '~880 MB',
    vramRequiredMB: 1100,
    vramFormatted: '~1.1 GB VRAM',
    contextWindow: '131.072 tokens',
    tier: 'speed',
    requiredFeatures: [],
  },
  {
    id: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
    name: 'Qwen 2.5 1.5B (Equilibrado)',
    tag: 'qwen2.5-1.5b',
    description: 'Equilibrio perfecto entre velocidad de respuesta y calidad en generación técnica en español.',
    downloadSize: '~950 MB',
    vramRequiredMB: 1630,
    vramFormatted: '~1.6 GB VRAM',
    contextWindow: '32.768 tokens',
    tier: 'balanced',
    requiredFeatures: [],
  },
  {
    id: 'Llama-3.2-3B-Instruct-q4f16_1-MLC',
    name: 'Llama 3.2 3B (Alta Calidad)',
    tag: 'llama-3.2-3b',
    description: 'Mayor capacidad de razonamiento y síntesis para equipos con GPU dedicada.',
    downloadSize: '~2.2 GB',
    vramRequiredMB: 3100,
    vramFormatted: '~3.0 GB VRAM',
    contextWindow: '131.072 tokens',
    tier: 'quality',
    requiredFeatures: [],
  },
] as const

export const CLIENT_ASR_MODELS: readonly ClientAsrModelDefinition[] = [
  {
    id: 'onnx-community/whisper-tiny',
    name: 'Whisper Tiny (Navegador)',
    description: 'Inferencia ultra rápida directamente en Web Worker con Transformers.js.',
    downloadSize: '~75 MB',
    badge: 'Transformers.js WebGPU/WASM',
    accuracy: 'Estándar',
    tier: 'speed',
  },
  {
    id: 'onnx-community/whisper-base',
    name: 'Whisper Base (Navegador)',
    description: 'Reconocimiento de voz equilibrado en español, ejecutado 100% en el cliente.',
    downloadSize: '~145 MB',
    badge: 'Transformers.js WebGPU/WASM',
    accuracy: 'Buena',
    tier: 'balanced',
  },
  {
    id: 'onnx-community/whisper-small',
    name: 'Whisper Small (Navegador)',
    description: 'Mayor precisión en transcripciones con vocabulario técnico o terminología compleja.',
    downloadSize: '~480 MB',
    badge: 'Transformers.js WebGPU/WASM',
    accuracy: 'Alta',
    tier: 'quality',
  },
] as const

export const DEFAULT_WEBLLM_MODEL = 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC'
export const DEFAULT_BROWSER_ASR_MODEL = 'onnx-community/whisper-base'

// Runtime catalog is authoritative. It is populated from AIModelCatalog by the settings loader.
// These constants are identifiers/defaults only; they are not an operational fallback.
let dynamicWebLLMModels: WebLLMModelDefinition[] = [...CLIENT_WEBLLM_MODELS]
let dynamicAsrModels: ClientAsrModelDefinition[] = [...CLIENT_ASR_MODELS]

export function setDynamicClientCatalog(models: ModelCatalogItem[]): void {
  if (!models || models.length === 0) return

  const webllm = models
    .filter((m) => m.provider === 'webllm' || (m.task_type === 'chat_writing' && m.id.includes('MLC')))
    .map((m) => ({
      id: m.id,
      name: m.name,
      tag: (m as any).tag || m.id.toLowerCase(),
      description: m.description,
      downloadSize: (m as any).download_size || (m as any).downloadSize || '~1 GB',
      vramRequiredMB: m.vram_required_mb || (m as any).vramRequiredMB || 1200,
      vramFormatted: m.vram_formatted || (m.vram_required_mb ? `~${m.vram_required_mb} MB VRAM` : '~1.2 GB VRAM'),
      contextWindow: m.context_window || '4k tokens',
      tier: ((m as any).tier as 'speed' | 'balanced' | 'quality') || 'balanced',
      requiredFeatures: m.required_features || [],
    }))

  const asr = models
    .filter((m) => m.provider === 'browser_asr' || m.provider === 'local')
    .map((m) => ({
      id: m.id,
      name: m.name,
      description: m.description,
      downloadSize: (m as any).download_size || (m as any).downloadSize || '~150 MB',
      badge: m.badge || 'Transformers.js WebGPU/WASM',
      accuracy: (m as any).accuracy || 'Buena',
      tier: ((m as any).tier as 'speed' | 'balanced' | 'quality') || 'balanced',
    }))

  if (webllm.length > 0) dynamicWebLLMModels = webllm
  if (asr.length > 0) dynamicAsrModels = asr
}

export function getClientWebLLMModels(): readonly WebLLMModelDefinition[] {
  return dynamicWebLLMModels
}

export function getClientAsrModels(): readonly ClientAsrModelDefinition[] {
  return dynamicAsrModels
}

export function isSupportedWebLLMModel(modelId: string): boolean {
  return dynamicWebLLMModels.some((m) => m.id === modelId)
}

export function isSupportedBrowserAsrModel(modelId: string): boolean {
  return dynamicAsrModels.some((m) => m.id === modelId)
}

export function findClientWebLLMModel(modelId: string): WebLLMModelDefinition | undefined {
  return dynamicWebLLMModels.find((m) => m.id === modelId)
}

export function findClientAsrModel(modelId: string): ClientAsrModelDefinition | undefined {
  return dynamicAsrModels.find((m) => m.id === modelId)
}
