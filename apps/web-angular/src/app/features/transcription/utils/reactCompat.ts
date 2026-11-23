/**
 * Tiny React-shaped helpers used while porting the transcription hooks, so the
 * Angular services can keep the exact same updater semantics as the React code.
 */

/** Equivalent of React `SetStateAction<T>`: a value or an updater of the previous value. */
export type SetStateAction<T> = T | ((prev: T) => T)

/** Resolves a {@link SetStateAction} against the previous value. */
export function resolveStateAction<T>(action: SetStateAction<T>, prev: T): T {
  return typeof action === 'function' ? (action as (prev: T) => T)(prev) : action
}

/** Equivalent of React `RefObject<T>` / `MutableRefObject<T>` (shared mutable box). */
export interface RefObject<T> {
  current: T
}
