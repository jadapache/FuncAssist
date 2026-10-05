import {
  API_BASE,
  handleResponse,
  type AIPromptTemplate,
  type AIRubric,
  type FeaturePayload,
  type GroundedResult,
} from '../client'

export const featuresApi = {
  generateStandup: (query?: string) =>
    fetch(`${API_BASE}/api/features/standup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query || 'Generate standup from recent work.' }),
    }).then((r) => handleResponse<GroundedResult>(r)),

  askProduct: (payload: {
    query: string
    sources: string[]
    document_ids?: string[]
    chat_context?: string
  }) =>
    fetch(`${API_BASE}/api/features/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  runPrdChecker: (payload: FeaturePayload) =>
    fetch(`${API_BASE}/api/features/prd-checker`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  runChangeImpact: (payload: FeaturePayload) =>
    fetch(`${API_BASE}/api/features/change-impact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  runQaFeature: (featureKey: string, payload: FeaturePayload) =>
    fetch(`${API_BASE}/api/features/qa/${featureKey}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  runMejoras: (payload: {
    query: string
    document_ids: string[]
    chat_context?: string
    sources?: string[]
  }) =>
    fetch(`${API_BASE}/api/features/mejoras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  inventarioDoc: (payload: FeaturePayload) =>
    fetch(`${API_BASE}/api/features/inventario`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  levantamientoDoc: (payload: FeaturePayload) =>
    fetch(`${API_BASE}/api/features/levantamiento`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<GroundedResult>(r)),

  getAiPrompts: () =>
    fetch(`${API_BASE}/api/ai/prompts`).then((r) =>
      handleResponse<{ prompts: AIPromptTemplate[] }>(r),
    ),

  getAiPrompt: (feature: string) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}`).then((r) =>
      handleResponse<AIPromptTemplate>(r),
    ),

  updateAiPrompt: (feature: string, payload: Partial<AIPromptTemplate>) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AIPromptTemplate>(r)),

  resetAiPrompt: (feature: string) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).then((r) => handleResponse<AIPromptTemplate>(r)),

  getAiRubrics: () =>
    fetch(`${API_BASE}/api/ai/rubrics`).then((r) =>
      handleResponse<{ rubrics: AIRubric[] }>(r),
    ),

  getAiRubric: (feature: string) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}`).then((r) =>
      handleResponse<AIRubric>(r),
    ),

  updateAiRubric: (feature: string, payload: { criteria: string[]; [key: string]: unknown }) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AIRubric>(r)),

  resetAiRubric: (feature: string) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).then((r) => handleResponse<AIRubric>(r)),
}
