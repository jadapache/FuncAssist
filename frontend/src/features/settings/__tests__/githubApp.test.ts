import { describe, expect, it } from 'vitest'
import {
  formatRepositorySelection,
  isReadOnlyLevel,
  parseGitHubAppDetails,
  validateGitHubApp,
} from '../utils/githubApp'

const PEM = '-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----'

describe('parseGitHubAppDetails', () => {
  it('interpreta los detalles de una GitHub App', () => {
    expect(
      parseGitHubAppDetails({
        auth_method: 'service_account',
        app_id: 12345,
        installation_id: '678',
        permissions: { metadata: 'read', contents: 'read' },
        repository_selection: 'selected',
        account_login: 'acme',
        configured_by: 'admin',
        configured_at: '2026-11-25T10:00:00Z',
      }),
    ).toEqual({
      authMethod: 'service_account',
      appId: '12345',
      installationId: '678',
      permissions: [
        { name: 'contents', level: 'read' },
        { name: 'metadata', level: 'read' },
      ],
      repositorySelection: 'selected',
      accountLogin: 'acme',
      configuredBy: 'admin',
      configuredAt: '2026-11-25T10:00:00Z',
    })
  })

  it('descarta valores con tipos inesperados', () => {
    const parsed = parseGitHubAppDetails({
      auth_method: 'oauth',
      permissions: ['read'],
      repository_selection: 'other',
    })
    expect(parsed.authMethod).toBeNull()
    expect(parsed.permissions).toEqual([])
    expect(parsed.repositorySelection).toBeNull()
    expect(parseGitHubAppDetails(undefined).appId).toBeNull()
  })
})

describe('formato', () => {
  it('describe el alcance de la instalación', () => {
    expect(formatRepositorySelection('selected')).toBe('Solo repositorios seleccionados')
    expect(formatRepositorySelection('all')).toBe('Todos los repositorios')
    expect(formatRepositorySelection(null)).toBe('Sin datos')
  })

  it('distingue permisos de solo lectura', () => {
    expect(isReadOnlyLevel('read')).toBe(true)
    expect(isReadOnlyLevel('write')).toBe(false)
  })
})

describe('validateGitHubApp', () => {
  it('acepta datos válidos y omite el installation id vacío', () => {
    expect(validateGitHubApp({ appId: ' 42 ', privateKey: PEM, installationId: '' })).toEqual({
      ok: true,
      payload: { app_id: '42', private_key: PEM, installation_id: undefined },
    })
    const withInstall = validateGitHubApp({ appId: '42', privateKey: PEM, installationId: '9' })
    expect(withInstall.ok && withInstall.payload.installation_id).toBe('9')
  })

  it('rechaza App ID, clave o installation id inválidos', () => {
    expect(validateGitHubApp({ appId: 'abc', privateKey: PEM, installationId: '' }).ok).toBe(false)
    expect(validateGitHubApp({ appId: '1', privateKey: 'no-pem', installationId: '' }).ok).toBe(false)
    expect(validateGitHubApp({ appId: '1', privateKey: PEM, installationId: 'x' }).ok).toBe(false)
  })
})
