import { apiClient } from '../../core/api/apiClient'
import type {
  AIPromptTemplate,
  AIRubric,
  FeaturePayload,
  GroundedResult,
} from '../client'

export const featuresApi = {
  generateStandup: (query?: string) =>
    apiClient.post<GroundedResult>('/api/features/standup', {
      query: query || 'Generate standup from recent work.',
    }),

  askProduct: (payload: {
    query: string
    sources: string[]
    document_ids?: string[]
    chat_context?: string
  }) => apiClient.post<GroundedResult>('/api/features/ask', payload),

  runPrdChecker: (payload: FeaturePayload) =>
    apiClient.post<GroundedResult>('/api/features/prd-checker', payload),

  runChangeImpact: (payload: FeaturePayload) =>
    apiClient.post<GroundedResult>('/api/features/change-impact', payload),

  runQaFeature: (featureKey: string, payload: FeaturePayload) =>
    apiClient.post<GroundedResult>(`/api/features/qa/${featureKey}`, payload),

  runMejoras: (payload: {
    query: string
    document_ids: string[]
    chat_context?: string
    sources?: string[]
  }) => apiClient.post<GroundedResult>('/api/features/mejoras', payload),

  inventarioDoc: (payload: FeaturePayload) =>
    apiClient.post<GroundedResult>('/api/features/inventario', payload),

  levantamientoDoc: (payload: FeaturePayload) =>
    apiClient.post<GroundedResult>('/api/features/levantamiento', payload),

  getAiPrompts: () =>
    apiClient.get<{ prompts: AIPromptTemplate[] }>('/api/ai/prompts'),

  getAiPrompt: (feature: string) =>
    apiClient.get<AIPromptTemplate>(`/api/ai/prompts/${feature}`),

  updateAiPrompt: (feature: string, payload: Partial<AIPromptTemplate>) =>
    apiClient.put<AIPromptTemplate>(`/api/ai/prompts/${feature}`, payload),

  resetAiPrompt: (feature: string) =>
    apiClient.post<AIPromptTemplate>(`/api/ai/prompts/${feature}/reset`),

  getAiRubrics: () =>
    apiClient.get<{ rubrics: AIRubric[] }>('/api/ai/rubrics'),

  getAiRubric: (feature: string) =>
    apiClient.get<AIRubric>(`/api/ai/rubrics/${feature}`),

  updateAiRubric: (feature: string, payload: { criteria: string[]; [key: string]: unknown }) =>
    apiClient.put<AIRubric>(`/api/ai/rubrics/${feature}`, payload),

  resetAiRubric: (feature: string) =>
    apiClient.post<AIRubric>(`/api/ai/rubrics/${feature}/reset`),
}

