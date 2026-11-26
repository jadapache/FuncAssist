export type RepositorySelection = 'all' | 'selected' | null

export type GitHubAppDetails = {
  authMethod: 'service_account' | null
  appId: string | null
  installationId: string | null
  permissions: { name: string; level: string }[]
  repositorySelection: RepositorySelection
  accountLogin: string | null
  configuredBy: string | null
  configuredAt: string | null
}

/** Read-only permissions the GitHub App needs and nothing more. */
export const GITHUB_APP_MINIMUM_PERMISSIONS: readonly string[] = [
  'Metadata',
  'Contents',
  'Pull requests',
  'Issues',
]

const asString = (value: unknown): string | null => {
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' && value.trim() ? value : null
}

export const parseGitHubAppDetails = (details: Record<string, unknown> | undefined): GitHubAppDetails => {
  const raw = details ?? {}
  const permissions =
    raw.permissions && typeof raw.permissions === 'object' && !Array.isArray(raw.permissions)
      ? Object.entries(raw.permissions as Record<string, unknown>)
          .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
          .map(([name, level]) => ({ name, level }))
          .sort((a, b) => a.name.localeCompare(b.name))
      : []
  const selection =
    raw.repository_selection === 'all' || raw.repository_selection === 'selected'
      ? raw.repository_selection
      : null
  return {
    authMethod: raw.auth_method === 'service_account' ? 'service_account' : null,
    appId: asString(raw.app_id),
    installationId: asString(raw.installation_id),
    permissions,
    repositorySelection: selection,
    accountLogin: asString(raw.account_login),
    configuredBy: asString(raw.configured_by),
    configuredAt: asString(raw.configured_at),
  }
}

export const formatRepositorySelection = (selection: RepositorySelection): string => {
  if (selection === 'selected') return 'Solo repositorios seleccionados'
  if (selection === 'all') return 'Todos los repositorios'
  return 'Sin datos'
}

/** Permission levels other than read are shown as a warning. */
export const isReadOnlyLevel = (level: string): boolean => level === 'read'

export type GitHubAppInput = { appId: string; privateKey: string; installationId: string }

export type GitHubAppResult =
  | { ok: true; payload: { app_id: string; private_key: string; installation_id?: string } }
  | { ok: false; error: string }

const PEM_PATTERN = /-----BEGIN (?:RSA )?PRIVATE KEY-----[\s\S]+-----END (?:RSA )?PRIVATE KEY-----/

export const validateGitHubApp = (input: GitHubAppInput): GitHubAppResult => {
  const appId = input.appId.trim()
  if (!/^\d+$/.test(appId)) return { ok: false, error: 'El App ID debe ser numérico.' }
  const privateKey = input.privateKey.trim()
  if (!PEM_PATTERN.test(privateKey)) {
    return { ok: false, error: 'La clave privada debe estar en formato PEM (-----BEGIN … PRIVATE KEY-----).' }
  }
  const installationId = input.installationId.trim()
  if (installationId && !/^\d+$/.test(installationId)) {
    return { ok: false, error: 'El Installation ID debe ser numérico.' }
  }
  return {
    ok: true,
    payload: {
      app_id: appId,
      private_key: privateKey,
      installation_id: installationId || undefined,
    },
  }
}
