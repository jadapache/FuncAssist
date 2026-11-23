import { authApi } from './modules/auth'
import { knowledgeApi } from '../features/knowledge/api/knowledgeApi'
import { aiSettingsApi } from '../features/settings/api/aiSettingsApi'
import { featuresApi } from './modules/features'
import { docAgentApi } from '../features/chat/api/docAgentApi'
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

export { API_BASE, getAuthHeaders, getAuthToken } from '../core/api/config'

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
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    Object.assign(error, { status: response.status })
    throw error
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
