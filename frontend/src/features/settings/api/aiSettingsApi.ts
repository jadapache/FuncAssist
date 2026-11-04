import {
  API_BASE,
  getAuthHeaders,
  handleResponse,
  type AISettings,
  type ModelCatalogResponse,
} from '../../../api/client'
import type {
  UserPreferences,
  ProviderCredentialInfo,
  McpServerInfo,
  McpServerPayload,
} from '../types'

export const aiSettingsApi = {
  getModelCatalog: (refresh?: boolean, provider?: string, task_type?: string) => {
    const params = new URLSearchParams()
    if (refresh) params.set('refresh', 'true')
    if (provider && provider !== 'all') params.set('provider', provider)
    if (task_type && task_type !== 'all') params.set('task_type', task_type)
    const qs = params.toString() ? `?${params.toString()}` : ''
    return fetch(`${API_BASE}/api/ai/models/catalog${qs}`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<ModelCatalogResponse>(r))
  },

  syncFrontierCatalog: (forceRemote: boolean = true) =>
    fetch(`${API_BASE}/api/ai/models/sync?force_remote=${forceRemote}`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ sync: Record<string, unknown>; catalog: ModelCatalogResponse }>(r)),

  getSyncStatus: () =>
    fetch(`${API_BASE}/api/ai/models/sync-status`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getAiSettings: () =>
    fetch(`${API_BASE}/api/ai/settings`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<AISettings>(r)),

  updateAiSettings: (payload: Record<string, string>) =>
    fetch(`${API_BASE}/api/ai/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AISettings>(r)),

  testAiConnection: (payload: Record<string, string>) =>
    fetch(`${API_BASE}/api/ai/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<{ ok: boolean; status?: string; message: string; response?: string }>(r)),

  listOllamaModels: (baseUrl?: string) =>
    fetch(`${API_BASE}/api/ai/ollama/models${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ''}`, {
      headers: { ...getAuthHeaders() },
    }).then(
      (r) => handleResponse<{ online: boolean; models: string[]; error?: string }>(r),
    ),

  pullOllamaModel: (name: string, baseUrl?: string) =>
    fetch(`${API_BASE}/api/ai/ollama/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ name, base_url: baseUrl }),
    }).then((r) => handleResponse<{ status: string; model: string }>(r)),

  deleteOllamaModel: (name: string, baseUrl?: string) =>
    fetch(`${API_BASE}/api/ai/ollama/${encodeURIComponent(name)}${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ''}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; message: string; model: string }>(r)),

  getPrompt: (feature: string) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  updatePrompt: (feature: string, payload: Record<string, unknown>) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getRubric: (feature: string) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  updateRubric: (feature: string, criteria: string[]) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ criteria }),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  listWhisperModels: () => Promise.resolve({ ok: true, models: [] }),

  downloadWhisperModel: (modelId: string) =>
    Promise.resolve({
      ok: true,
      model_id: modelId,
      file_path: '',
      message: 'Modelo listo para ejecución.',
    }),

  deleteWhisperModel: (_modelId: string) =>
    Promise.resolve({
      ok: true,
      message: 'Modelo eliminado.',
    }),

  listBuiltinModels: () =>
    aiSettingsApi.getModelCatalog(false, 'local', 'chat_writing').then((res) => ({
      ok: true,
      models: (res?.models || []).map((m) => ({
        id: m.id,
        name: m.name,
        size: m.size || 'Variable',
        tokens: m.context_window || '',
        description: m.description,
        filename: m.raw_id,
        is_downloaded: Boolean(m.is_downloaded),
        disk_size_mb: m.disk_size_mb || 0,
        file_path: null,
      })),
    })),

  getBuiltinDownloadTasks: (): Promise<{
    ok: boolean
    tasks: Array<{
      id: string
      title: string
      progress: number
      status: string
      stageText?: string
      speedOrSize?: string
      eta?: string | null
    }>
  }> =>
    Promise.resolve({
      ok: true,
      tasks: [],
    }),

  downloadBuiltinModel: (modelId: string) =>
    Promise.resolve({
      ok: true,
      model_id: modelId,
      file_path: '',
      message: 'Descarga iniciada.',
    }),

  cancelBuiltinModelDownload: (modelId: string) =>
    Promise.resolve({
      ok: true,
      model_id: modelId,
      message: 'Descarga cancelada.',
    }),

  deleteBuiltinModel: (modelId: string) =>
    fetch(`${API_BASE}/api/ai/builtin/${encodeURIComponent(modelId)}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; message: string }>(r)),

  getUserPreferences: () =>
    fetch(`${API_BASE}/api/me/preferences`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<UserPreferences>(r)),

  updateUserPreferences: (prefs: Partial<UserPreferences>) =>
    fetch(`${API_BASE}/api/me/preferences`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(prefs),
    }).then((r) => handleResponse<UserPreferences>(r)),

  listProviderCredentials: () =>
    fetch(`${API_BASE}/api/me/provider-credentials`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<ProviderCredentialInfo[]>(r)),

  setProviderCredential: (provider: string, apiKey: string) =>
    fetch(`${API_BASE}/api/me/provider-credentials/${encodeURIComponent(provider)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ api_key: apiKey }),
    }).then((r) => handleResponse<ProviderCredentialInfo>(r)),

  validateProviderCredential: (provider: string) =>
    fetch(`${API_BASE}/api/me/provider-credentials/${encodeURIComponent(provider)}/validate`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; valid?: boolean; provider: string; status?: string }>(r)),

  deleteProviderCredential: (provider: string) =>
    fetch(`${API_BASE}/api/me/provider-credentials/${encodeURIComponent(provider)}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; provider: string }>(r)),

  listMcpServers: () =>
    fetch(`${API_BASE}/api/me/mcp-servers`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<McpServerInfo[]>(r)),

  createMcpServer: (payload: McpServerPayload) =>
    fetch(`${API_BASE}/api/me/mcp-servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<McpServerInfo>(r)),

  updateMcpServer: (id: string, payload: Partial<McpServerPayload & { status?: string }>) =>
    fetch(`${API_BASE}/api/me/mcp-servers/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<McpServerInfo>(r)),

  deleteMcpServer: (id: string) =>
    fetch(`${API_BASE}/api/me/mcp-servers/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; deleted_id: string }>(r)),

  testMcpServer: (id: string) =>
    fetch(`${API_BASE}/api/me/mcp-servers/${encodeURIComponent(id)}/test`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; status: string; endpoint_url: string }>(r)),
}

