/**
 * Browser features that only exist in a secure context (HTTPS or http://localhost).
 *
 * On a corporate LAN the app is often opened as http://<server IP>. There the browser hides
 * WebGPU, the Cache API, Web Locks, `crypto.randomUUID` and `navigator.clipboard`. These helpers
 * let the app keep working (with fallbacks) and explain what needs HTTPS.
 */

export function isSecureOrigin(): boolean {
  return typeof globalThis !== 'undefined' && globalThis.isSecureContext === true
}

/** RFC 4122 v4 UUID from `crypto.getRandomValues`, which is available on plain HTTP too. */
export function randomUUIDFallback(): string {
  const bytes = new Uint8Array(16)
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes)
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/**
 * `crypto.randomUUID` is undefined outside secure contexts; the app calls it to create message
 * and artifact ids. Install a compatible implementation once at startup.
 */
export function installRandomUUIDPolyfill(): void {
  if (typeof crypto === 'undefined' || typeof crypto.randomUUID === 'function') return
  try {
    Object.defineProperty(crypto, 'randomUUID', {
      value: randomUUIDFallback as Crypto['randomUUID'],
      configurable: true,
      writable: true,
    })
  } catch {
    // Read-only Crypto object: callers that need ids should use randomUUIDFallback directly.
  }
}

/**
 * Copies text to the clipboard. Uses the async Clipboard API when available (secure contexts)
 * and falls back to a hidden textarea + `execCommand('copy')` on plain HTTP.
 */
export async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Permission denied or unavailable: try the legacy path below.
    }
  }
  if (typeof document === 'undefined') return false
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '-1000px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(textarea)
  }
}
