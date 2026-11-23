import { useEffect, useState } from 'react'

const CHECK_INTERVAL_MS = 5 * 60 * 1000
const MIN_CHECK_GAP_MS = 30 * 1000

/** Path of the module script an index.html loads (the hashed bundle entry in production). */
export function extractEntryScriptPath(html: string, baseHref: string): string | null {
  const tags = html.match(/<script\b[^>]*>/gi) ?? []
  for (const tag of tags) {
    if (!/type=["']module["']/i.test(tag)) continue
    const src = /src=["']([^"']+)["']/i.exec(tag)
    if (src) {
      try {
        return new URL(src[1], baseHref).pathname
      } catch {
        return src[1]
      }
    }
  }
  return null
}

function loadedEntryScriptPath(): string | null {
  const el = document.querySelector<HTMLScriptElement>('script[type="module"][src]')
  if (!el) return null
  try {
    return new URL(el.src, window.location.href).pathname
  } catch {
    return el.getAttribute('src')
  }
}

/**
 * True once the server's index.html points at a different bundle than the one running in this tab,
 * i.e. a new version was deployed. Checked when the tab regains focus and every few minutes.
 */
export function useNewVersionAvailable(): boolean {
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    if (import.meta.env.DEV) return
    const loaded = loadedEntryScriptPath()
    if (!loaded) return

    let stopped = false
    let lastCheck = 0
    const check = async () => {
      const now = Date.now()
      if (stopped || now - lastCheck < MIN_CHECK_GAP_MS) return
      lastCheck = now
      try {
        const res = await fetch(`/index.html?_=${now}`, { cache: 'no-store' })
        if (!res.ok) return
        const latest = extractEntryScriptPath(await res.text(), window.location.href)
        if (!stopped && latest && latest !== loaded) {
          stopped = true
          setAvailable(true)
        }
      } catch {
        // Offline or server restarting: try again on the next focus/interval.
      }
    }

    const onFocus = () => {
      if (document.visibilityState === 'visible') void check()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    const timer = window.setInterval(() => void check(), CHECK_INTERVAL_MS)
    return () => {
      stopped = true
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
      window.clearInterval(timer)
    }
  }, [])

  return available
}
