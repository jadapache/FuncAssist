import { useLayoutEffect, useRef } from 'react'

/** Ref that always holds the latest value, for callbacks that must not change identity. */
export function useLatest<T>(value: T) {
  const ref = useRef(value)
  useLayoutEffect(() => {
    ref.current = value
  })
  return ref
}
