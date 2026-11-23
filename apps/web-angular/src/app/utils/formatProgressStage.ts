export function formatProgressStage(
  rawText?: string,
  progress: number = 0,
): string {
  if (!rawText) {
    return `Descargando componentes (${progress}%)`
  }

  const lower = rawText.toLowerCase()

  if (
    lower.includes('fetching param cache') ||
    lower.includes('fetched')
  ) {
    const match = rawText.match(/\[(\d+\/\d+)\]/)
    const part = match ? ` [${match[1]}]` : ''

    return `Descargando pesos a la caché${part}`
  }

  if (lower.includes('loading model from cache')) {
    return 'Cargando modelo desde caché local'
  }

  if (lower.includes('compil') || lower.includes('wasm')) {
    return 'Compilando módulos WebGPU'
  }

  if (lower.includes('shader')) {
    return 'Inicializando shaders de aceleración'
  }

  if (
    lower.includes('finish') ||
    lower.includes('complete') ||
    progress >= 100
  ) {
    return 'Carga completada'
  }

  return `Descargando componentes (${progress}%)`
}