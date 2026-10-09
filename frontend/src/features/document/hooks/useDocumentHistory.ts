import { useCallback, useRef, useState } from 'react'

interface DocumentHistoryOptions {
  maxStackSize?: number
}

interface DocumentHistoryState {
  content: string
  /** Current active index in the history stack */
  pointer: number
  /** Full history stack */
  stack: string[]
  canUndo: boolean
  canRedo: boolean
  isDirty: boolean
}

/**
 * Hook for managing undo/redo history of document content.
 * Maintains an immutable stack of snapshots with a movable pointer.
 */
export function useDocumentHistory(
  initialContent: string = '',
  options: DocumentHistoryOptions = {},
) {
  const { maxStackSize = 100 } = options

  const [stack, setStack] = useState<string[]>([initialContent])
  const [pointer, setPointer] = useState(0)
  const savedContentRef = useRef<string>(initialContent)

  const currentContent = stack[pointer] ?? initialContent
  const canUndo = pointer > 0
  const canRedo = pointer < stack.length - 1
  const isDirty = currentContent !== savedContentRef.current

  /**
   * Push a new content snapshot. Trims any redo history past the current pointer.
   */
  const pushContent = useCallback(
    (newContent: string) => {
      setStack((prev) => {
        const trimmed = prev.slice(0, pointer + 1)
        const next = [...trimmed, newContent]
        // Enforce max stack size
        if (next.length > maxStackSize) {
          next.shift()
          return next
        }
        return next
      })
      setPointer((prev) => {
        const newPtr = Math.min(prev + 1, maxStackSize - 1)
        return newPtr
      })
    },
    [pointer, maxStackSize],
  )

  const undo = useCallback(() => {
    setPointer((prev) => Math.max(0, prev - 1))
  }, [])

  const redo = useCallback(() => {
    setPointer((prev) => Math.min(stack.length - 1, prev + 1))
  }, [stack.length])

  /**
   * Mark the current content as "saved" so isDirty resets.
   */
  const markSaved = useCallback(() => {
    savedContentRef.current = stack[pointer] ?? initialContent
  }, [stack, pointer, initialContent])

  /**
   * Reset the entire history to a new initial value (e.g., loading a new conversation).
   */
  const resetHistory = useCallback((content: string) => {
    setStack([content])
    setPointer(0)
    savedContentRef.current = content
  }, [])

  const state: DocumentHistoryState = {
    content: currentContent,
    pointer,
    stack,
    canUndo,
    canRedo,
    isDirty,
  }

  return {
    ...state,
    pushContent,
    undo,
    redo,
    markSaved,
    resetHistory,
  }
}
