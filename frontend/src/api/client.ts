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

export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export const handleResponse = async <T,>(response: Response): Promise<T> => {
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // ignore
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export const api = {
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
