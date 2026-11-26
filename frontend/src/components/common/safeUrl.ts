/**
 * Decides what the chat may do with a URL found in model output.
 *
 * Model output can carry text taken from external content (tickets, documents, web pages). A markdown
 * image or link is a way to send data out: the browser requests the URL, query string included. So images
 * only load from the application itself and links to other sites are shown with their destination.
 */

export type UrlVerdict =
  | { kind: 'local' }
  | { kind: 'allowed'; host: string }
  | { kind: 'external'; host: string; hasQuery: boolean }
  | { kind: 'blocked' }

const SAFE_DATA_IMAGE = /^data:image\/(?:png|jpe?g|gif|webp);base64,[a-z0-9+/=\s]+$/i
const SCHEME = /^([a-z][a-z0-9+.-]*):/i

function hostMatches(host: string, allowed: string[]): boolean {
  return allowed.some((entry) => host === entry || host.endsWith(`.${entry}`))
}

export function parseAllowedHosts(raw: string | undefined | null): string[] {
  return (raw ?? '')
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
}

export function classifyUrl(
  raw: string | undefined | null,
  options: { allowedHosts?: string[]; currentHost?: string; forImage?: boolean } = {},
): UrlVerdict {
  const value = (raw ?? '').trim()
  if (!value) return { kind: 'blocked' }
  const allowedHosts = options.allowedHosts ?? []

  if (SAFE_DATA_IMAGE.test(value)) return options.forImage ? { kind: 'local' } : { kind: 'blocked' }

  const scheme = SCHEME.exec(value)?.[1]?.toLowerCase()
  if (scheme && scheme !== 'http' && scheme !== 'https') {
    // mailto links are harmless to open; everything else (javascript:, data:, file:, blob:, ...) is not.
    return scheme === 'mailto' && !options.forImage ? { kind: 'local' } : { kind: 'blocked' }
  }

  if (!scheme && !value.startsWith('//')) return { kind: 'local' } // relative path, anchor or query only

  let parsed: URL
  try {
    parsed = new URL(value.startsWith('//') ? `https:${value}` : value)
  } catch {
    return { kind: 'blocked' }
  }
  if (parsed.username || parsed.password) return { kind: 'blocked' }

  const host = parsed.hostname.toLowerCase()
  if (!host) return { kind: 'blocked' }
  const current = (options.currentHost ?? '').toLowerCase().split(':')[0]
  if (current && host === current) return { kind: 'local' }
  if (hostMatches(host, allowedHosts)) return { kind: 'allowed', host }
  return { kind: 'external', host, hasQuery: parsed.search.length > 1 || parsed.hash.length > 1 }
}

/** Whether an image with this URL may be requested by the browser. */
export function canLoadImage(verdict: UrlVerdict): boolean {
  return verdict.kind === 'local' || verdict.kind === 'allowed'
}

/** Whether a link may be rendered as clickable. External links with parameters are not. */
export function canOpenLink(verdict: UrlVerdict): boolean {
  if (verdict.kind === 'local' || verdict.kind === 'allowed') return true
  return verdict.kind === 'external' && !verdict.hasQuery
}
