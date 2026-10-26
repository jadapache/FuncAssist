import { AUTH_TOKEN_KEY } from '../constants/app'
import { authApi } from './modules/auth'
import { knowledgeApi } from '../features/knowledge/api/knowledgeApi'
import { aiSettingsApi } from '../features/settings/api/aiSettingsApi'
import { featuresApi } from './modules/features'
import { docAgentApi } from '../features/document/api/docAgentApi'
import { integrationsApi } from '../features/integrations/api/integrationsApi'
import { templatesApi } from '../features/settings/api/templatesApi'
import { settingsApi } from '../features/settings/api/settingsApi'
import { userApi } from './modules/user'
import { transcriptionApi } from '../features/transcription/api/transcriptionApi'
import { draftsApi } from '../features/document/api/draftsApi'

// 1. Re-export Feature & Domain Types
export type { UserProfile, UserRole } from './modules/user'
export type { FeaturePayload, AppSettings, IntegrationInfo, TestConnectionResult, AuthMethod } from '../types/app'
export type * from '../features/knowledge/types'
export type * from '../features/settings/types'
export type * from '../features/document/types'
export type * from '../features/transcription/api/transcriptionApi'

export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  (typeof window !== 'undefined' &&
  (window.location.protocol === 'tauri:' ||
    window.location.hostname === 'tauri.localhost' ||
    '__TAURI__' in window ||
    '__TAURI_INTERNALS__' in window)
    ? 'http://127.0.0.1:6728'
    : '')

export const getAuthHeaders = (): Record<string, string> => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export type AuthUser = {
  id: string
  username: string
  email?: string
  full_name?: string
  role?: string
  status?: string
  created_at?: string
}

export type AuthResponse = {
  token?: string
  status?: string
  message?: string
  user: AuthUser
}

export const handleResponse = async <T,>(response: Response): Promise<T> => {
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // ignore
    }
    if (Array.isArray(detail)) {
      detail = detail
        .map((item: unknown) => {
          if (typeof item === 'string') return item
          if (typeof item === 'object' && item !== null) {
            const errObj = item as { loc?: (string | number)[]; type?: string; msg?: string }
            if (
              errObj.loc?.includes('username') &&
              (errObj.type === 'string_pattern_mismatch' || errObj.msg?.includes('pattern'))
            ) {
              return 'El nombre de usuario admite solo letras y números'
            }
            if (errObj.msg) {
              return errObj.msg.replace(/^Value error,\s*/i, '')
            }
          }
          return JSON.stringify(item)
        })
        .join('. ')
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export const api = {
  ...authApi,
  ...userApi,
  ...knowledgeApi,
  ...aiSettingsApi,
  ...featuresApi,
  ...docAgentApi,
  ...integrationsApi,
  ...templatesApi,
  ...settingsApi,
  ...transcriptionApi,
  ...draftsApi,
}

export const apiClient = api
