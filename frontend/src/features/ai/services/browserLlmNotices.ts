/** Non-fatal notices from the in-browser LLM (e.g. "switched to a lighter model"), shown as toasts. */

export interface BrowserLlmNotice {
  title: string
  message: string
}

type Listener = (notice: BrowserLlmNotice) => void

const listeners = new Set<Listener>()

export function subscribeBrowserLlmNotices(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function emitBrowserLlmNotice(notice: BrowserLlmNotice): void {
  for (const listener of listeners) {
    try {
      listener(notice)
    } catch {
      // A broken listener must not break inference.
    }
  }
}
