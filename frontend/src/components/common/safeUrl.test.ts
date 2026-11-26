import { describe, expect, it } from 'vitest'
import { canLoadImage, canOpenLink, classifyUrl, parseAllowedHosts } from './safeUrl'

const OPTIONS = { allowedHosts: ['docs.example.com', 'atlassian.net'], currentHost: 'app.example.com:6728' }

describe('classifyUrl', () => {
  it.each(['', '   ', null, undefined])('blocks an empty value (%s)', (value) => {
    expect(classifyUrl(value as string | null | undefined, OPTIONS)).toEqual({ kind: 'blocked' })
  })

  it.each([
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'vbscript:x',
    'file:///etc/passwd',
    'blob:https://x/uuid',
    'data:text/html;base64,PHNjcmlwdD4=',
    'ftp://example.com/x',
  ])('blocks the dangerous scheme in %s', (url) => {
    expect(classifyUrl(url, OPTIONS)).toEqual({ kind: 'blocked' })
  })

  it('treats relative paths, anchors and query-only references as local', () => {
    for (const url of ['/img/logo.png', 'img/logo.png', './a.png', '../a.png', '#section', '?q=1']) {
      expect(classifyUrl(url, OPTIONS)).toEqual({ kind: 'local' })
    }
  })

  it('treats the application host as local, with or without a port', () => {
    expect(classifyUrl('https://app.example.com/x.png', OPTIONS)).toEqual({ kind: 'local' })
    expect(classifyUrl('https://APP.example.com:6728/x', OPTIONS)).toEqual({ kind: 'local' })
  })

  it('allows listed hosts and their subdomains only', () => {
    expect(classifyUrl('https://docs.example.com/guide', OPTIONS)).toEqual({ kind: 'allowed', host: 'docs.example.com' })
    expect(classifyUrl('https://acme.atlassian.net/browse/A-1', OPTIONS)).toEqual({ kind: 'allowed', host: 'acme.atlassian.net' })
    expect(classifyUrl('https://evilatlassian.net/x', OPTIONS)).toMatchObject({ kind: 'external' })
    expect(classifyUrl('https://atlassian.net.evil.example/x', OPTIONS)).toMatchObject({ kind: 'external' })
  })

  it('reports other hosts as external and notes parameters', () => {
    expect(classifyUrl('https://evil.example/page', OPTIONS)).toEqual({ kind: 'external', host: 'evil.example', hasQuery: false })
    expect(classifyUrl('https://evil.example/log?d=secret', OPTIONS)).toEqual({ kind: 'external', host: 'evil.example', hasQuery: true })
    expect(classifyUrl('https://evil.example/page#frag', OPTIONS)).toMatchObject({ hasQuery: true })
    expect(classifyUrl('//evil.example/x?d=1', OPTIONS)).toMatchObject({ kind: 'external', host: 'evil.example' })
  })

  it('blocks credentials in the URL and malformed hosts', () => {
    expect(classifyUrl('https://user:pass@evil.example/x', OPTIONS)).toEqual({ kind: 'blocked' })
    expect(classifyUrl('https://', OPTIONS)).toEqual({ kind: 'blocked' })
    expect(classifyUrl('http://[::1', OPTIONS)).toEqual({ kind: 'blocked' })
  })

  it('accepts small data images only for images', () => {
    const png = 'data:image/png;base64,iVBORw0KGgo='
    expect(classifyUrl(png, { ...OPTIONS, forImage: true })).toEqual({ kind: 'local' })
    expect(classifyUrl(png, OPTIONS)).toEqual({ kind: 'blocked' })
    expect(classifyUrl('data:image/svg+xml;base64,PHN2Zz4=', { ...OPTIONS, forImage: true })).toEqual({ kind: 'blocked' })
  })

  it('allows mailto links but never as images', () => {
    expect(classifyUrl('mailto:a@b.co', OPTIONS)).toEqual({ kind: 'local' })
    expect(classifyUrl('mailto:a@b.co', { ...OPTIONS, forImage: true })).toEqual({ kind: 'blocked' })
  })

  it('works without options', () => {
    expect(classifyUrl('https://evil.example/x')).toMatchObject({ kind: 'external' })
    expect(classifyUrl('/x')).toEqual({ kind: 'local' })
  })
})

describe('what a verdict permits', () => {
  it('loads images only from the application or listed hosts', () => {
    expect(canLoadImage({ kind: 'local' })).toBe(true)
    expect(canLoadImage({ kind: 'allowed', host: 'docs.example.com' })).toBe(true)
    expect(canLoadImage({ kind: 'external', host: 'evil.example', hasQuery: false })).toBe(false)
    expect(canLoadImage({ kind: 'blocked' })).toBe(false)
  })

  it('opens links unless they are blocked or external with parameters', () => {
    expect(canOpenLink({ kind: 'local' })).toBe(true)
    expect(canOpenLink({ kind: 'allowed', host: 'docs.example.com' })).toBe(true)
    expect(canOpenLink({ kind: 'external', host: 'evil.example', hasQuery: false })).toBe(true)
    expect(canOpenLink({ kind: 'external', host: 'evil.example', hasQuery: true })).toBe(false)
    expect(canOpenLink({ kind: 'blocked' })).toBe(false)
  })
})

describe('parseAllowedHosts', () => {
  it('splits, trims, lowercases and drops empties', () => {
    expect(parseAllowedHosts(' Docs.Example.com, ,atlassian.net ,')).toEqual(['docs.example.com', 'atlassian.net'])
    expect(parseAllowedHosts('')).toEqual([])
    expect(parseAllowedHosts(undefined)).toEqual([])
  })
})
