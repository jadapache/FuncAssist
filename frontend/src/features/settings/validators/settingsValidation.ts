export type ValidationResult = {
  isValid: boolean
  error?: string
}

export function normalizeOllamaUrl(url?: string): string {
  if (!url) return 'http://localhost:11434'
  const trimmed = url.trim()
  return trimmed || 'http://localhost:11434'
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

  if (provider === 'ollama' && ollamaUrl) {
    const target = normalizeOllamaUrl(ollamaUrl)
    if (!isValidHttpUrl(target)) {
      return {
        isValid: false,
        error: 'La dirección URL de Ollama debe ser una URL válida (ejemplo: http://localhost:11434).',
      }
    }
  }

  // Key check for cloud providers if no key has been saved and input is empty
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
