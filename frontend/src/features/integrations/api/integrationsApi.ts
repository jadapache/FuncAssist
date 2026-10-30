import {
  API_BASE,
  getAuthHeaders,
  handleResponse,
  type IntegrationInfo,
  type TestConnectionResult,
} from '../../../api/client'
import type { JiraConnectionStatus } from '../../settings/types'

export const integrationsApi = {
  getIntegrations: () =>
    fetch(`${API_BASE}/api/integrations`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<IntegrationInfo[]>(r)),

  getIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  startOAuth: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/oauth/start`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{ authorization_url: string; state: string; auth_method: string }>(r),
    ),

  connectWithPat: (
    id: string,
    payload: { token: string; email?: string; base_url?: string; selected_repos?: string[] },
  ) =>
    fetch(`${API_BASE}/api/integrations/${id}/pat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  testIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/test`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<TestConnectionResult>(r),
    ),

  disconnectIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/disconnect`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<IntegrationInfo>(r),
    ),

  getIssues: () =>
    fetch(`${API_BASE}/api/integrations/jira/issues`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{ issues: Array<Record<string, unknown>> }>(r),
    ),

  getProjects: () =>
    fetch(`${API_BASE}/api/integrations/jira/projects`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{
        projects: Array<{ id: string; key: string; name: string; selected: boolean }>
      }>(r),
    ),

  updateProjects: (selected_projects: string[]) =>
    fetch(`${API_BASE}/api/integrations/jira/projects`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ selected_projects }),
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  autoSelectJiraProject: () =>
    fetch(`${API_BASE}/api/integrations/jira/auto-select-project`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<IntegrationInfo>(r),
    ),

  getPullRequests: (id: string = 'github') =>
    fetch(`${API_BASE}/api/integrations/${id}/pull-requests`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{ pull_requests: Array<Record<string, unknown>> }>(r),
    ),

  getRepositories: (id: string = 'github') =>
    fetch(`${API_BASE}/api/integrations/${id}/repositories`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{
        repositories: Array<{
          full_name: string
          name: string
          private: boolean
          selected: boolean
          html_url: string
        }>
      }>(r),
    ),

  updateRepositories: (id: string, selected_repos: string[]) =>
    fetch(`${API_BASE}/api/integrations/${id}/repositories`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ selected_repos }),
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  syncIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/sync`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<Record<string, unknown>>(r),
    ),

  getSyncCache: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/sync`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<Record<string, unknown>>(r)),

  getJiraStatus: () =>
    fetch(`${API_BASE}/api/me/integrations/jira/status`, {
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<JiraConnectionStatus>(r)),

  startUserJiraOAuth: () =>
    fetch(`${API_BASE}/api/me/integrations/jira/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ auth_method: 'oauth' }),
    }).then((r) => handleResponse<{ authorization_url: string; state: string; auth_method: string }>(r)),

  connectUserJiraPat: (payload: { token: string; email?: string; jira_url?: string }) =>
    fetch(`${API_BASE}/api/me/integrations/jira/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ auth_method: 'pat', ...payload }),
    }).then((r) => handleResponse<{ ok: boolean; status: string }>(r)),

  connectJiraOAuth: (payload: { code: string; state: string; redirect_uri?: string }) =>
    fetch(`${API_BASE}/api/me/integrations/jira/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<JiraConnectionStatus>(r)),

  disconnectJiraOAuth: () =>
    fetch(`${API_BASE}/api/me/integrations/jira`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ ok: boolean; disconnected: boolean }>(r)),
}

