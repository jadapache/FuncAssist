import { api, type ModelCatalogItem } from '../../../api/client'
import type {
  HardwareProfile,
  ModelEvaluation,
  ModelPreference,
  WebLLMModelDefinition,
} from '../types/webLlm'

let cachedModels: WebLLMModelDefinition[] = []

export function getCachedWebLLMModels(): WebLLMModelDefinition[] {
  return cachedModels
}

export function findWebLLMModel(modelId: string): WebLLMModelDefinition | undefined {
  return cachedModels.find((item) => item.id === modelId)
}

interface NavigatorWithMemory extends Navigator {
  deviceMemory?: number
}

function resolveHardwareTier(memoryGB: number, hasWebGPU: boolean): 'low' | 'medium' | 'high' {
  if (!hasWebGPU || memoryGB < 4) {
    return 'low'
  }
  if (memoryGB >= 8) {
    return 'high'
  }
  return 'medium'
}

export async function detectHardwareProfile(): Promise<HardwareProfile> {
  const nav = typeof navigator !== 'undefined' ? (navigator as NavigatorWithMemory) : null
  const deviceMemoryGB = nav?.deviceMemory ?? 4
  const hardwareConcurrency = nav?.hardwareConcurrency ?? 4

  if (!nav || !('gpu' in nav) || !nav.gpu) {
    return {
      hasWebGPU: false,
      hasShaderF16: false,
      adapterName: 'No WebGPU Support',
      deviceMemoryGB,
      hardwareConcurrency,
      maxBufferSizeMB: 0,
      tier: 'low',
    }
  }

  try {
    const adapterPromise = nav.gpu.requestAdapter()
    const timeoutPromise = new Promise<null>((resolve) => setTimeout(() => resolve(null), 1500))
    const adapter = await Promise.race([adapterPromise, timeoutPromise])
    if (!adapter) {
      return {
        hasWebGPU: false,
        hasShaderF16: false,
        adapterName: 'WebGPU Adapter Unavailable',
        deviceMemoryGB,
        hardwareConcurrency,
        maxBufferSizeMB: 0,
        tier: 'low',
      }
    }

    const gpuAdapter = adapter as GPUAdapter & {
      info?: { description?: string; vendor?: string }
      requestAdapterInfo?: () => Promise<{ description?: string; vendor?: string }>
    }
    const hasShaderF16 = adapter.features.has('shader-f16')
    const maxBufferSizeMB = Math.round(adapter.limits.maxStorageBufferBindingSize / (1024 * 1024))
    const adapterInfo = typeof gpuAdapter.requestAdapterInfo === 'function'
      ? await gpuAdapter.requestAdapterInfo().catch(() => null)
      : gpuAdapter.info ?? null
    const adapterName = adapterInfo?.description || adapterInfo?.vendor || 'WebGPU Device'
    const tier = resolveHardwareTier(deviceMemoryGB, true)

    return {
      hasWebGPU: true,
      hasShaderF16,
      adapterName,
      deviceMemoryGB,
      hardwareConcurrency,
      maxBufferSizeMB,
      tier,
    }
  } catch {
    return {
      hasWebGPU: false,
      hasShaderF16: false,
      adapterName: 'Error detecting WebGPU',
      deviceMemoryGB,
      hardwareConcurrency,
      maxBufferSizeMB: 0,
      tier: 'low',
    }
  }
}

export function evaluateModel(
  model: WebLLMModelDefinition,
  profile: HardwareProfile,
  preference: ModelPreference,
): ModelEvaluation {
  if (!profile.hasWebGPU) {
    return {
      model,
      isCompatible: false,
      isRecommended: false,
      reason: 'El navegador o dispositivo no cuenta con aceleración WebGPU activa.',
    }
  }

  if (false && model.requiredFeatures?.includes('shader-f16') && !profile.hasShaderF16) {
    return {
      model,
      isCompatible: false,
      isRecommended: false,
      reason: 'El adaptador gráfico no soporta shader-f16 requerido por este modelo.',
    }
  }

  if (profile.deviceMemoryGB < 4 && model.vramRequiredMB > 1200) {
    return {
      model,
      isCompatible: true,
      isRecommended: false,
      reason: `Memoria de equipo ajustada (${profile.deviceMemoryGB} GB). Se recomienda un modelo menor a 1.2 GB VRAM.`,
    }
  }

  const matchesPreference = model.tier === preference
  const isRecommended = matchesPreference || (preference === 'balanced' && model.id === 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC')

  return {
    model,
    isCompatible: true,
    isRecommended,
    reason: isRecommended
      ? 'Alineado con el perfil de memoria del equipo y preferencia seleccionada.'
      : `Compatible con WebGPU (${model.vramFormatted}).`,
  }
}

export function evaluateAllModels(
  models: WebLLMModelDefinition[],
  profile: HardwareProfile,
  preference: ModelPreference = 'balanced',
): ModelEvaluation[] {
  return models.map((m) => evaluateModel(m, profile, preference))
}

export function selectOptimalModel(
  models: WebLLMModelDefinition[],
  profile: HardwareProfile,
  preference: ModelPreference = 'balanced',
): WebLLMModelDefinition {
  const evaluations = evaluateAllModels(models, profile, preference)
  const recommended = evaluations.find((e) => e.isCompatible && e.isRecommended)
  if (recommended) {
    return recommended.model
  }

  const anyCompatible = evaluations.find((e) => e.isCompatible)
  if (anyCompatible) {
    return anyCompatible.model
  }

  return models[0]
}

export async function loadWebLLMModelsFromBackend(): Promise<WebLLMModelDefinition[]> {
  try {
    const res = await api.getModelCatalog(false, 'local', 'chat_writing')
    if (res?.models && res.models.length > 0) {
      cachedModels = res.models.map((m: ModelCatalogItem) => {
        const vramNum = typeof m.vram_required_mb === 'number' ? m.vram_required_mb : 1630
        return {
          id: m.id,
          name: m.name,
          tag: m.raw_id || m.id,
          description: m.description || '',
          downloadSize: m.size || '~950 MB',
          vramRequiredMB: vramNum,
          vramFormatted:
            m.vram_formatted ||
            (vramNum < 1000 ? `~${vramNum} MB VRAM` : `~${(vramNum / 1024).toFixed(1)} GB VRAM`),
          contextWindow: m.context_window || '32.768 tokens',
          tier: (m.tier as 'speed' | 'balanced' | 'quality') || 'balanced',
          requiredFeatures: m.required_features || [],
        }
      })
      return cachedModels
    }
  } catch {
    // Return cached models if offline or network error occurs
  }
  return cachedModels
}
