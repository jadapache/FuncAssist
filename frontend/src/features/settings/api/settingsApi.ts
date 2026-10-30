import {
  API_BASE,
  getAuthHeaders,
  handleResponse,
  type AppSettings,
} from '../../../api/client'

export const settingsApi = {
  getSettings: () =>
    fetch(`${API_BASE}/api/settings`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<AppSettings>(r)),

  updateSettings: (payload: AppSettings) =>
    fetch(`${API_BASE}/api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AppSettings>(r)),

  getJiraOAuth: () =>
    fetch(`${API_BASE}/api/settings/jira-oauth`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{
        configured: boolean
        client_id_set: boolean
        client_secret_set: boolean
        redirect_uri: string
        scopes?: string[]
        scope_guide?: Array<{
          scope: string
          label: string
          where: string
          required: boolean
        }>
      }>(r),
    ),

  saveJiraOAuth: (payload: { client_id: string; client_secret?: string; redirect_uri?: string }) =>
    fetch(`${API_BASE}/api/settings/jira-oauth`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getGitHubOAuth: () =>
    fetch(`${API_BASE}/api/settings/github-oauth`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{
        configured: boolean
        client_id_set: boolean
        client_secret_set: boolean
        redirect_uri: string
      }>(r),
    ),

  saveGitHubOAuth: (payload: { client_id: string; client_secret?: string; redirect_uri?: string }) =>
    fetch(`${API_BASE}/api/settings/github-oauth`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getGitLabOAuth: () =>
    fetch(`${API_BASE}/api/settings/gitlab-oauth`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{
        configured: boolean
        client_id_set: boolean
        client_secret_set: boolean
        redirect_uri: string
        base_url?: string
      }>(r),
    ),

  saveGitLabOAuth: (payload: {
    client_id: string
    client_secret?: string
    redirect_uri?: string
    base_url?: string
  }) =>
    fetch(`${API_BASE}/api/settings/gitlab-oauth`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  health: () =>
    fetch(`${API_BASE}/api/health`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ status: string; app: string }>(r)),
}
