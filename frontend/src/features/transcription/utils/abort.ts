/** Error used for user cancellations, recognisable with `isAbortError`. */
export function abortError(message = 'Transcripción cancelada por el usuario.'): Error {
  const err = new Error(message)
  err.name = 'AbortError'
  return err
}

export function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === 'AbortError'
}

export function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw abortError()
}
