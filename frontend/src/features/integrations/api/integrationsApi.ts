import {
  API_BASE,
  handleResponse,
  type IntegrationInfo,
  type TestConnectionResult,
} from '../../../api/client'

export const integrationsApi = {
  getIntegrations: () =>
    fetch(`${API_BASE}/api/integrations`).then((r) => handleResponse<IntegrationInfo[]>(r)),

  getIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}`).then((r) => handleResponse<IntegrationInfo>(r)),

  startOAuth: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/oauth/start`, { method: 'POST' }).then((r) =>
      handleResponse<{ authorization_url: string; state: string; auth_method: string }>(r),
    ),

  connectWithPat: (
    id: string,
    payload: { token: string; email?: string; base_url?: string; selected_repos?: string[] },
  ) =>
    fetch(`${API_BASE}/api/integrations/${id}/pat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  testIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/test`, { method: 'POST' }).then((r) =>
      handleResponse<TestConnectionResult>(r),
    ),

  disconnectIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/disconnect`, { method: 'POST' }).then((r) =>
      handleResponse<IntegrationInfo>(r),
    ),

  getIssues: () =>
    fetch(`${API_BASE}/api/integrations/jira/issues`).then((r) =>
      handleResponse<{ issues: Array<Record<string, unknown>> }>(r),
    ),

  getProjects: () =>
    fetch(`${API_BASE}/api/integrations/jira/projects`).then((r) =>
      handleResponse<{
        projects: Array<{ id: string; key: string; name: string; selected: boolean }>
      }>(r),
    ),

  updateProjects: (selected_projects: string[]) =>
    fetch(`${API_BASE}/api/integrations/jira/projects`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_projects }),
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  autoSelectJiraProject: () =>
    fetch(`${API_BASE}/api/integrations/jira/auto-select-project`, { method: 'POST' }).then((r) =>
      handleResponse<IntegrationInfo>(r),
    ),

  getPullRequests: (id: string = 'github') =>
    fetch(`${API_BASE}/api/integrations/${id}/pull-requests`).then((r) =>
      handleResponse<{ pull_requests: Array<Record<string, unknown>> }>(r),
    ),

  getRepositories: (id: string = 'github') =>
    fetch(`${API_BASE}/api/integrations/${id}/repositories`).then((r) =>
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_repos }),
    }).then((r) => handleResponse<IntegrationInfo>(r)),

  syncIntegration: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/sync`, { method: 'POST' }).then((r) =>
      handleResponse<Record<string, unknown>>(r),
    ),

  getSyncCache: (id: string) =>
    fetch(`${API_BASE}/api/integrations/${id}/sync`).then((r) => handleResponse<Record<string, unknown>>(r)),
}
