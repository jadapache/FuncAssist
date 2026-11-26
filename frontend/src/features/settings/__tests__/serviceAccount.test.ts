import { describe, expect, it } from 'vitest'
import {
  formatConfiguredAt,
  formatExpiry,
  parseServiceAccountDetails,
  validateBaseUrl,
} from '../utils/serviceAccount'

describe('parseServiceAccountDetails', () => {
  it('interpreta los detalles de una cuenta de servicio', () => {
    expect(
      parseServiceAccountDetails({
        auth_method: 'service_account',
        scopes: ['read_api', 'read_user'],
        expires_at: '2027-01-31T00:00:00Z',
        expiry: 'ok',
        configured_by: 'admin',
        configured_at: '2026-11-20T10:00:00Z',
      }),
    ).toEqual({
      authMethod: 'service_account',
      scopes: ['read_api', 'read_user'],
      expiresAt: '2027-01-31T00:00:00Z',
      expiry: 'ok',
      configuredBy: 'admin',
      configuredAt: '2026-11-20T10:00:00Z',
    })
  })

  it('descarta valores con tipos inesperados', () => {
    expect(
      parseServiceAccountDetails({ auth_method: 'x', scopes: ['a', 1, null], expiry: 'raro', expires_at: 5 }),
    ).toEqual({
      authMethod: null,
      scopes: ['a'],
      expiresAt: null,
      expiry: 'none',
      configuredBy: null,
      configuredAt: null,
    })
  })

  it('tolera detalles ausentes', () => {
    expect(parseServiceAccountDetails(undefined).scopes).toEqual([])
  })
})

describe('formatExpiry', () => {
  it('muestra sin caducidad', () => {
    expect(formatExpiry('none', null)).toEqual({ label: 'Sin caducidad', tone: 'neutral' })
  })

  it('muestra la fecha de caducidad', () => {
    expect(formatExpiry('ok', '2027-01-31T00:00:00Z')).toEqual({
      label: 'Caduca el 2027-01-31',
      tone: 'neutral',
    })
  })

  it('avisa cuando caduca pronto', () => {
    expect(formatExpiry('expiring', '2026-12-01').tone).toBe('warning')
  })

  it('marca como caducado', () => {
    expect(formatExpiry('expired', '2026-01-01')).toEqual({ label: 'Caducado', tone: 'danger' })
  })
})

describe('formatConfiguredAt', () => {
  it('devuelve solo la fecha', () => {
    expect(formatConfiguredAt('2026-11-20T10:00:00Z')).toBe('2026-11-20')
  })

  it('devuelve null si no es una fecha', () => {
    expect(formatConfiguredAt(null)).toBeNull()
    expect(formatConfiguredAt('ayer')).toBeNull()
  })
})

describe('validateBaseUrl', () => {
  it('acepta vacío como valor por defecto', () => {
    expect(validateBaseUrl('  ')).toEqual({ ok: true, baseUrl: undefined })
  })

  it('acepta https y quita barras finales', () => {
    expect(validateBaseUrl('https://gitlab.example.com/')).toEqual({
      ok: true,
      baseUrl: 'https://gitlab.example.com',
    })
  })

  it('rechaza http', () => {
    expect(validateBaseUrl('http://gitlab.example.com')).toEqual({
      ok: false,
      error: 'La URL de GitLab debe usar HTTPS.',
    })
  })

  it('rechaza texto que no es una URL', () => {
    expect(validateBaseUrl('gitlab').ok).toBe(false)
  })
})
