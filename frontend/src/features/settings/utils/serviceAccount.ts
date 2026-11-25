export type ServiceAccountExpiry = 'none' | 'ok' | 'expiring' | 'expired'

export type ServiceAccountDetails = {
  authMethod: 'service_account' | 'oauth' | null
  scopes: string[]
  expiresAt: string | null
  expiry: ServiceAccountExpiry
  configuredBy: string | null
  configuredAt: string | null
}

export type ExpiryDisplay = {
  label: string
  tone: 'neutral' | 'warning' | 'danger'
}

const EXPIRY_VALUES: readonly ServiceAccountExpiry[] = ['none', 'ok', 'expiring', 'expired']

const asString = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() ? value : null

export const parseServiceAccountDetails = (
  details: Record<string, unknown> | undefined,
): ServiceAccountDetails => {
  const raw = details ?? {}
  const authMethod =
    raw.auth_method === 'service_account' || raw.auth_method === 'oauth' ? raw.auth_method : null
  const expiry = EXPIRY_VALUES.find((value) => value === raw.expiry) ?? 'none'
  return {
    authMethod,
    scopes: Array.isArray(raw.scopes)
      ? raw.scopes.filter((scope): scope is string => typeof scope === 'string')
      : [],
    expiresAt: asString(raw.expires_at),
    expiry,
    configuredBy: asString(raw.configured_by),
    configuredAt: asString(raw.configured_at),
  }
}

const formatDate = (iso: string): string => iso.slice(0, 10)

export const formatExpiry = (expiry: ServiceAccountExpiry, expiresAt: string | null): ExpiryDisplay => {
  if (expiry === 'expired') return { label: 'Caducado', tone: 'danger' }
  if (expiry === 'expiring') return { label: 'Caduca pronto', tone: 'warning' }
  if (!expiresAt) return { label: 'Sin caducidad', tone: 'neutral' }
  return { label: `Caduca el ${formatDate(expiresAt)}`, tone: 'neutral' }
}

export const formatConfiguredAt = (iso: string | null): string | null =>
  iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? formatDate(iso) : null

export type BaseUrlResult = { ok: true; baseUrl: string | undefined } | { ok: false; error: string }

/** An empty value means the default host; anything else must be a valid https URL. */
export const validateBaseUrl = (value: string): BaseUrlResult => {
  const trimmed = value.trim()
  if (!trimmed) return { ok: true, baseUrl: undefined }
  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    return { ok: false, error: 'La URL de GitLab no es válida.' }
  }
  if (parsed.protocol !== 'https:') {
    return { ok: false, error: 'La URL de GitLab debe usar HTTPS.' }
  }
  return { ok: true, baseUrl: trimmed.replace(/\/+$/, '') }
}
