/**
 * Coordination of the models that use the GPU inside this tab, and across tabs.
 *
 * The in-browser LLM (WebLLM) and the in-browser Whisper worker both allocate GPU memory. Loading
 * one while the other is still resident is a common cause of "out of memory / device lost". Each
 * consumer registers a release callback; before loading, a consumer asks the others to release.
 */

type ReleaseFn = () => Promise<void> | void

const consumers = new Map<string, ReleaseFn>()

/** Registers a GPU consumer. Returns an unregister function. */
export function registerGpuConsumer(name: string, release: ReleaseFn): () => void {
  consumers.set(name, release)
  return () => {
    if (consumers.get(name) === release) consumers.delete(name)
  }
}

/** Asks every other consumer to free its GPU memory (each decides whether it can, e.g. if idle). */
export async function releaseOtherGpuConsumers(except: string): Promise<void> {
  const others = [...consumers.entries()].filter(([name]) => name !== except)
  await Promise.all(
    others.map(async ([name, release]) => {
      try {
        await release()
      } catch (err) {
        console.warn(`No se pudo liberar la GPU de "${name}":`, err)
      }
    }),
  )
}

interface LockManagerLike {
  request: (
    name: string,
    options: { ifAvailable?: boolean; mode?: 'exclusive' | 'shared' },
    callback: (lock: unknown) => Promise<void>,
  ) => Promise<unknown>
}

/**
 * Exclusive lock shared by all tabs of the app (Web Locks API), so that only one tab keeps a large
 * model in GPU memory. Returns:
 *  - a release function when the lock was acquired,
 *  - `null` when another tab holds it,
 *  - a no-op release when Web Locks are not available (plain HTTP or old browsers): no coordination.
 */
export async function acquireTabGpuLock(name: string): Promise<(() => void) | null> {
  const locks = (typeof navigator !== 'undefined' ? (navigator as unknown as { locks?: LockManagerLike }).locks : undefined)
  if (!locks || typeof locks.request !== 'function') return () => undefined

  return new Promise<(() => void) | null>((resolve) => {
    let release: () => void = () => undefined
    const held = new Promise<void>((done) => {
      release = done
    })
    locks
      .request(name, { ifAvailable: true, mode: 'exclusive' }, async (lock) => {
        if (!lock) {
          resolve(null)
          return
        }
        resolve(release)
        await held // keep the lock until released
      })
      .catch(() => resolve(() => undefined))
  })
}
