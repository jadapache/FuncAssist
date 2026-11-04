export type ValidationResult = {
  isValid: boolean
  error?: string
}

export function validateRemoteEndpointUrl(urlString: string, allowHttp = false): ValidationResult {
  const trimmed = urlString.trim()
  if (!trimmed) return { isValid: false, error: 'La URL del endpoint remoto es obligatoria.' }
  let parsed: URL
  try { parsed = new URL(trimmed) } catch { return { isValid: false, error: 'Formato de URL inválido.' } }
  if (parsed.protocol !== 'https:' && (!allowHttp || parsed.protocol !== 'http:')) {
    return { isValid: false, error: 'El endpoint remoto debe utilizar protocolo HTTPS.' }
  }
  const host = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, '')
  const privateIpv4 = /^(10\.|127\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)
  if (host === 'localhost' || host === '::1' || host === '0.0.0.0' || host.endsWith('.local') || host.endsWith('.internal') || privateIpv4) {
    return { isValid: false, error: 'Endpoints locales y redes privadas no están permitidos.' }
  }
  return { isValid: true }
}

export function normalizeOllamaUrl(url?: string): string {
  if (!url) return ''
  return url.trim()
}

export function isValidHttpUrl(stringUrl: string): boolean {
  try {
    const url = new URL(stringUrl)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
}

export type AiSettingsValidationParams = {
  provider: string
  model: string
  ollamaUrl?: string
  groqKey?: string
  geminiKey?: string
  openaiKey?: string
  claudeKey?: string
  isKeyConfigured?: boolean
}

export function validateAiSettingsPayload(params: AiSettingsValidationParams): ValidationResult {
  const { provider, model, ollamaUrl, groqKey, geminiKey, openaiKey, claudeKey, isKeyConfigured } = params

  if (!model || !model.trim()) {
    return {
      isValid: false,
      error: 'Debes seleccionar o especificar un identificador de modelo válido.',
    }
  }

  if (model.toLowerCase().endsWith('.gguf')) {
    return {
      isValid: false,
      error: 'Los modelos en formato GGUF no están admitidos. Usa WebLLM en navegador o una API externa.',
    }
  }

  if (provider === 'ollama' || provider === 'ollama_remote') {
    const target = normalizeOllamaUrl(ollamaUrl)
    const urlCheck = validateRemoteEndpointUrl(target, false)
    if (!urlCheck.isValid) {
      return {
        isValid: false,
        error: urlCheck.error || 'Debes indicar una URL remota HTTPS válida para Ollama.',
      }
    }
  }

  if (['groq', 'gemini', 'openai', 'claude'].includes(provider)) {
    let key = ''
    if (provider === 'groq') key = groqKey || ''
    if (provider === 'gemini') key = geminiKey || ''
    if (provider === 'openai') key = openaiKey || ''
    if (provider === 'claude') key = claudeKey || ''

    if (!isKeyConfigured && !key.trim()) {
      return {
        isValid: false,
        error: `Debes ingresar una clave de API válida para el proveedor ${provider.toUpperCase()}.`,
      }
    }
  }

  return { isValid: true }
}

export type PatValidationParams = {
  token: string
  email?: string
  baseUrl?: string
}

export function validatePatPayload(integrationId: string, params: PatValidationParams): ValidationResult {
  const { token, email, baseUrl } = params

  if (!token || !token.trim()) {
    return {
      isValid: false,
      error: 'El Personal Access Token (PAT) es obligatorio.',
    }
  }

  if (integrationId === 'jira') {
    if (!email || !email.trim()) {
      return {
        isValid: false,
        error: 'El correo electrónico de Atlassian es obligatorio para Jira.',
      }
    }
    if (!isValidEmail(email)) {
      return {
        isValid: false,
        error: 'Ingresa un correo electrónico con formato válido para Atlassian.',
      }
    }
    if (!baseUrl || !baseUrl.trim()) {
      return {
        isValid: false,
        error: 'La URL del sitio Jira es obligatoria (ejemplo: https://mi-dominio.atlassian.net).',
      }
    }
    if (!isValidHttpUrl(baseUrl.trim())) {
      return {
        isValid: false,
        error: 'La URL de Jira debe incluir el protocolo https:// o http://.',
      }
    }
  }

  if (integrationId === 'gitlab' && baseUrl && baseUrl.trim()) {
    if (!isValidHttpUrl(baseUrl.trim())) {
      return {
        isValid: false,
        error: 'La URL personalizada de GitLab debe ser válida (ejemplo: https://gitlab.mi-empresa.com).',
      }
    }
  }

  return { isValid: true }
}
