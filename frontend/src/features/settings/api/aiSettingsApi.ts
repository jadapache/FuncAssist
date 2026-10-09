import {
  API_BASE,
  handleResponse,
  type AISettings,
  type ModelCatalogResponse,
} from '../../../api/client'

export const aiSettingsApi = {
  getModelCatalog: (refresh?: boolean, provider?: string, task_type?: string) => {
    const params = new URLSearchParams()
    if (refresh) params.set('refresh', 'true')
    if (provider && provider !== 'all') params.set('provider', provider)
    if (task_type && task_type !== 'all') params.set('task_type', task_type)
    const qs = params.toString() ? `?${params.toString()}` : ''
    return fetch(`${API_BASE}/api/ai/models/catalog${qs}`).then((r) =>
      handleResponse<ModelCatalogResponse>(r),
    )
  },

  syncFrontierCatalog: (forceRemote: boolean = true) =>
    fetch(`${API_BASE}/api/ai/models/sync?force_remote=${forceRemote}`, {
      method: 'POST',
    }).then((r) => handleResponse<{ sync: Record<string, unknown>; catalog: ModelCatalogResponse }>(r)),

  getSyncStatus: () =>
    fetch(`${API_BASE}/api/ai/models/sync-status`).then((r) =>
      handleResponse<Record<string, unknown>>(r),
    ),

  getAiSettings: () =>
    fetch(`${API_BASE}/api/ai/settings`).then((r) => handleResponse<AISettings>(r)),

  updateAiSettings: (payload: Record<string, string>) =>
    fetch(`${API_BASE}/api/ai/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AISettings>(r)),

  testAiConnection: (payload: Record<string, string>) =>
    fetch(`${API_BASE}/api/ai/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<{ ok: boolean; status?: string; message: string; response?: string }>(r)),

  listOllamaModels: (baseUrl?: string) =>
    fetch(`${API_BASE}/api/ai/ollama/models${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ''}`).then(
      (r) => handleResponse<{ online: boolean; models: string[]; error?: string }>(r),
    ),

  pullOllamaModel: (name: string, baseUrl?: string) =>
    fetch(`${API_BASE}/api/ai/ollama/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, base_url: baseUrl }),
    }).then((r) => handleResponse<{ status: string; model: string }>(r)),

  deleteOllamaModel: (name: string, baseUrl?: string) =>
    fetch(`${API_BASE}/api/ai/ollama/${encodeURIComponent(name)}${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ''}`, {
      method: 'DELETE',
    }).then((r) => handleResponse<{ ok: boolean; message: string; model: string }>(r)),

  getPrompt: (feature: string) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}`).then((r) => handleResponse<Record<string, unknown>>(r)),

  updatePrompt: (feature: string, payload: Record<string, unknown>) =>
    fetch(`${API_BASE}/api/ai/prompts/${feature}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getRubric: (feature: string) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}`).then((r) => handleResponse<Record<string, unknown>>(r)),

  updateRubric: (feature: string, criteria: string[]) =>
    fetch(`${API_BASE}/api/ai/rubrics/${feature}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ criteria }),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  listWhisperModels: () =>
    fetch(`${API_BASE}/api/ai/whisper/models`).then((r) =>
      handleResponse<{ ok: boolean; models: Array<{ id: string; name: string; size: string; accuracy: string; description: string; is_downloaded: boolean; disk_size_mb: number }> }>(r),
    ),

  downloadWhisperModel: (modelId: string) =>
    fetch(`${API_BASE}/api/ai/whisper/download/${modelId}`, {
      method: 'POST',
    }).then((r) => handleResponse<{ ok: boolean; model_id: string; file_path: string; message: string }>(r)),

  deleteWhisperModel: (modelId: string) =>
    fetch(`${API_BASE}/api/ai/whisper/${modelId}`, {
      method: 'DELETE',
    }).then((r) => handleResponse<{ ok: boolean; message: string }>(r)),

  listBuiltinModels: () =>
    fetch(`${API_BASE}/api/ai/builtin/models`).then((r) =>
      handleResponse<{ ok: boolean; models: Array<{ id: string; name: string; size: string; tokens?: string; description: string; filename?: string; is_downloaded: boolean; disk_size_mb: number; file_path: string | null }> }>(r),
    ),

  getBuiltinDownloadTasks: () =>
    fetch(`${API_BASE}/api/ai/builtin/tasks`).then((r) =>
      handleResponse<{
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
      }>(r),
    ),

  downloadBuiltinModel: (modelId: string) =>
    fetch(`${API_BASE}/api/ai/builtin/download/${encodeURIComponent(modelId)}`, {
      method: 'POST',
    }).then((r) => handleResponse<{ ok: boolean; model_id: string; file_path: string; message: string }>(r)),

  cancelBuiltinModelDownload: (modelId: string) =>
    fetch(`${API_BASE}/api/ai/builtin/cancel/${encodeURIComponent(modelId)}`, {
      method: 'POST',
    }).then((r) => handleResponse<{ ok: boolean; model_id: string; message: string }>(r)),

  deleteBuiltinModel: (modelId: string) =>
    fetch(`${API_BASE}/api/ai/builtin/${encodeURIComponent(modelId)}`, {
      method: 'DELETE',
    }).then((r) => handleResponse<{ ok: boolean; message: string }>(r)),
}

