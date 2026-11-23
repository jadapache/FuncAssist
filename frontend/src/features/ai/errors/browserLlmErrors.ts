/**
 * Precise classification of in-browser LLM (WebLLM) failures.
 *
 * Several unrelated problems used to be reported as "the GPU ran out of memory": an insecure
 * origin (no WebGPU on http://<IP>), a GPU timeout reset by Windows, a prompt longer than the
 * model's context window. Each now has its own kind and message, and the original error is kept.
 */

export type BrowserLlmErrorKind =
  | 'insecure_context'
  | 'no_webgpu'
  | 'unsupported_gpu'
  | 'out_of_memory'
  | 'gpu_timeout'
  | 'gpu_lost'
  | 'context_window'
  | 'busy_other_tab'
  | 'other'

/** Kinds where retrying with a lighter model is worth it. */
export const GPU_PRESSURE_KINDS: ReadonlySet<BrowserLlmErrorKind> = new Set(['out_of_memory', 'gpu_timeout', 'gpu_lost'])

export class BrowserLlmError extends Error {
  readonly kind: BrowserLlmErrorKind
  readonly modelId: string | null
  readonly original: unknown

  constructor(kind: BrowserLlmErrorKind, message: string, modelId: string | null = null, original: unknown = null) {
    super(message)
    this.name = 'BrowserLlmError'
    this.kind = kind
    this.modelId = modelId
    this.original = original
  }
}

export function isBrowserLlmError(err: unknown): err is BrowserLlmError {
  return err instanceof BrowserLlmError || (typeof err === 'object' && err !== null && (err as { name?: string }).name === 'BrowserLlmError')
}

function rawMessage(err: unknown): string {
  if (err instanceof Error) return `${err.name}: ${err.message}`
  if (typeof err === 'string') return err
  try {
    return JSON.stringify(err)
  } catch {
    return String(err)
  }
}

export function classifyBrowserLlmError(err: unknown, secureContext = true): BrowserLlmErrorKind {
  if (isBrowserLlmError(err)) return err.kind
  const text = rawMessage(err)
  if (/ContextWindowSizeExceeded|context\s*window|prompt\s*tokens?\s*exceed/i.test(text)) return 'context_window'
  if (/shader-f16|FeatureSupportError|required\s*feature|maxStorageBufferBindingSize|maxBufferSize|exceeds?\s*(the\s*)?(device|adapter)?\s*limit/i.test(text)) {
    return 'unsupported_gpu'
  }
  if (/webgpu|navigator\.gpu|requestAdapter|no\s*(suitable|compatible)?\s*(gpu|adapter)/i.test(text) && /not\s*(supported|available|found)|unsupported|unavailable|undefined|null|cannot\s*find|no\s*(suitable|compatible)/i.test(text)) {
    return secureContext ? 'no_webgpu' : 'insecure_context'
  }
  if (/device[_\s-]*hung|0x887a0006|\btdr\b/i.test(text)) return 'gpu_timeout'
  if (/out\s*of\s*memory|outofmemory|insufficient\s*memory|failed\s*to\s*allocate|allocation\s*failed|GPUOutOfMemoryError|0x8007000e/i.test(text)) {
    return 'out_of_memory'
  }
  if (/device\s*(was\s*)?lost|device[_\s-]*removed|0x887a0005|dxgi_error|already\s*been\s*disposed|instance\s*reference\s*has\s*been\s*disposed/i.test(text)) {
    return 'gpu_lost'
  }
  return 'other'
}

export function browserLlmErrorMessage(kind: BrowserLlmErrorKind, modelName?: string | null, fallback?: string): string {
  const model = modelName ? ` (${modelName})` : ''
  switch (kind) {
    case 'insecure_context':
      return 'Los modelos en el navegador necesitan que la aplicación se abra por HTTPS. Estás entrando por una dirección http:// de la red, donde el navegador desactiva la GPU (WebGPU). Pide a TI la dirección HTTPS de la aplicación o elige un proveedor en la nube en Configuración.'
    case 'no_webgpu':
      return 'Este navegador o equipo no tiene WebGPU disponible, necesario para los modelos en el navegador. Usa Chrome o Edge actualizados con la aceleración por hardware activada, o elige un proveedor en la nube en Configuración.'
    case 'unsupported_gpu':
      return `La tarjeta gráfica de este equipo no admite las funciones que necesita el modelo${model}. Elige otro modelo o un proveedor en la nube en Configuración.`
    case 'out_of_memory':
      return `La GPU se quedó sin memoria al ejecutar el modelo${model}. Cierra otras pestañas de la aplicación y otros programas que usen la GPU, elige un modelo más ligero (Llama 3.2 1B) o un proveedor en la nube.`
    case 'gpu_timeout':
      return `La GPU tardó demasiado en responder y Windows la reinició mientras ejecutaba el modelo${model}. Suele pasar con textos largos en tarjetas gráficas integradas: prueba con un texto más corto, un modelo más ligero (Llama 3.2 1B) o un proveedor en la nube.`
    case 'gpu_lost':
      return `La GPU dejó de responder al ejecutar el modelo${model}, normalmente por falta de memoria gráfica. Cierra otras pestañas de la aplicación, elige un modelo más ligero (Llama 3.2 1B) o un proveedor en la nube.`
    case 'context_window':
      return 'El texto es demasiado largo para el modelo del navegador (admite unos 4.000 tokens entre la pregunta y la respuesta). Acorta el documento o la conversación, o elige un proveedor en la nube para textos extensos.'
    case 'busy_other_tab':
      return 'Otra pestaña de la aplicación está usando el modelo en el navegador. Solo una pestaña puede tenerlo cargado a la vez para no agotar la memoria de la GPU: ciérrala o espera unos minutos a que lo libere.'
    default:
      return fallback || 'Error al ejecutar el modelo de lenguaje en el navegador.'
  }
}

/** Wraps any failure into a BrowserLlmError, logging the original error for diagnosis. */
export function toBrowserLlmError(err: unknown, modelId: string | null, modelName?: string | null): BrowserLlmError {
  if (isBrowserLlmError(err)) return err
  const secure = typeof globalThis === 'undefined' || globalThis.isSecureContext !== false
  const kind = classifyBrowserLlmError(err, secure)
  console.error(`[WebLLM] Error original (${kind}) con el modelo ${modelId ?? 'desconocido'}:`, err)
  const fallback = err instanceof Error ? err.message : undefined
  return new BrowserLlmError(kind, browserLlmErrorMessage(kind, modelName, fallback), modelId, err)
}
