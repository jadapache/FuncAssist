/**
 * API layer barrel export.
 * Re-exports base types, helpers, and domain sub-modules for backwards-compatibility.
 */

export * from './client'
export { api, apiClient } from './client'
export { authApi } from './modules/auth'
export { knowledgeApi } from './modules/knowledge'
export { aiSettingsApi } from './modules/aiSettings'
export { featuresApi } from './modules/features'
export { docAgentApi } from './modules/docAgent'
export { integrationsApi } from './modules/integrations'
export { templatesApi } from './modules/templates'
export { settingsApi } from './modules/settings'
export { transcriptionApi } from '../features/transcription/api/transcriptionApi'
