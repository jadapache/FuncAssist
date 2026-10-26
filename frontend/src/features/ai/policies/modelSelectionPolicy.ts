import type {
  HardwareProfile,
  ModelEvaluation,
  ModelPreference,
  WebLLMModelDefinition,
} from '../types/webLlm'

export const WEBLLM_MODELS_CATALOG: WebLLMModelDefinition[] = [
  {
    id: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
    name: 'Qwen 2.5 1.5B (Equilibrado / Recomendado)',
    tag: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
    description: 'Equilibrio idóneo entre consumo de memoria y razonamiento para generación de historias de usuario y criterios Gherkin.',
    downloadSize: '~950 MB',
    vramRequiredMB: 1630,
    vramFormatted: '~1.6 GB VRAM',
    contextWindow: '32.768 tokens',
    tier: 'balanced',
    requiredFeatures: ['shader-f16'],
  },
  {
    id: 'Llama-3.2-1B-Instruct-q4f16_1-MLC',
    name: 'Llama 3.2 1B (Ultra Ligero / Rápido)',
    tag: 'Llama-3.2-1B-Instruct-q4f16_1-MLC',
    description: 'Arranque casi instantáneo y mínimo consumo de memoria. Recomendado para equipos con GPU integrada básica o laptops.',
    downloadSize: '~700 MB',
    vramRequiredMB: 880,
    vramFormatted: '~880 MB VRAM',
    contextWindow: '131.072 tokens',
    tier: 'speed',
    requiredFeatures: ['shader-f16'],
  },
  {
    id: 'Qwen2.5-3B-Instruct-q4f16_1-MLC',
    name: 'Qwen 2.5 3B (Alta Calidad QA)',
    tag: 'Qwen2.5-3B-Instruct-q4f16_1-MLC',
    description: 'Máxima profundidad lógica en análisis de casos de prueba y matrices de trazabilidad complejas en español.',
    downloadSize: '~1.9 GB',
    vramRequiredMB: 2505,
    vramFormatted: '~2.5 GB VRAM',
    contextWindow: '32.768 tokens',
    tier: 'quality',
    requiredFeatures: ['shader-f16'],
  },
  {
    id: 'SmolLM2-1.7B-Instruct-q4f16_1-MLC',
    name: 'SmolLM2 1.7B (Compacto y Ágil)',
    tag: 'SmolLM2-1.7B-Instruct-q4f16_1-MLC',
    description: 'Modelo altamente eficiente de Hugging Face, optimizado para redacción directa y resúmenes ejecutivos.',
    downloadSize: '~1.0 GB',
    vramRequiredMB: 1774,
    vramFormatted: '~1.7 GB VRAM',
    contextWindow: '8.192 tokens',
    tier: 'speed',
    requiredFeatures: ['shader-f16'],
  },
  {
    id: 'Qwen2.5-Coder-1.5B-Instruct-q4f16_1-MLC',
    name: 'Qwen 2.5 Coder 1.5B (Especializado Técnico)',
    tag: 'Qwen2.5-Coder-1.5B-Instruct-q4f16_1-MLC',
    description: 'Alineado con estructuras JSON, pasos de prueba automatizados y especificaciones técnicas de endpoints.',
    downloadSize: '~950 MB',
    vramRequiredMB: 1630,
    vramFormatted: '~1.6 GB VRAM',
    contextWindow: '32.768 tokens',
    tier: 'balanced',
    requiredFeatures: ['shader-f16'],
  },
]

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
    const adapter = await nav.gpu.requestAdapter()
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

  if (model.requiredFeatures?.includes('shader-f16') && !profile.hasShaderF16) {
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
