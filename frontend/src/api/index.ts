/**
 * API layer barrel export.
 * Re-exports base types, helpers, and domain sub-modules for backwards-compatibility.
 */

export * from './client'
export { api, apiClient } from './client'
export { userApi } from './modules/user'
export { featuresApi } from './modules/features'
export { knowledgeApi } from '../features/knowledge/api/knowledgeApi'
export { aiSettingsApi } from '../features/settings/api/aiSettingsApi'
export { docAgentApi } from '../features/document/api/docAgentApi'
export { integrationsApi } from '../features/integrations/api/integrationsApi'
export { templatesApi } from '../features/settings/api/templatesApi'
export { settingsApi } from '../features/settings/api/settingsApi'
export { transcriptionApi } from '../features/transcription/api/transcriptionApi'
