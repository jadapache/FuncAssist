export type AuthMethod = 'oauth' | 'pat' | 'api_key' | 'none'

export type IntegrationInfo = {
  id: string
  name: string
  auth_method: AuthMethod
  connected: boolean
  account_email?: string | null
  account_name?: string | null
  workspace_name?: string | null
  base_url?: string | null
  available_projects?: string[]
  selected_projects?: string[]
  has_projects?: boolean
  has_repositories?: boolean
  requires_base_url?: boolean
  supports_pat?: boolean
  supports_oauth?: boolean
  configured?: boolean
  error_message?: string | null
  last_sync_at?: string | null

  // UI status / helper fields
  status?: 'connected' | 'not_configured' | 'error' | string
  workspace_label?: string
  account_label?: string
  description?: string
  auth_methods?: string[]
  capabilities?: string[]
  oauth_configured?: boolean
  details?: Record<string, unknown>
  error?: string | null
}

export type TestConnectionResult = {
  ok: boolean
  message: string
  error_code?: string
  suggested_action?: string
  requires_reconnect?: boolean
}

export type AppSettings = {
  display_name?: string
  jira?: Record<string, unknown>
  github?: Record<string, unknown>
  gitlab?: Record<string, unknown>
  [key: string]: unknown
}

export type FeaturePayload = {
  query: string
  document_ids: string[]
  chat_context?: string
  sources?: string[]
}
