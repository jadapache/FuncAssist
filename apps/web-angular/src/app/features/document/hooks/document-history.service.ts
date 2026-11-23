import { Injectable, computed, signal, untracked } from '@angular/core'

export interface DocumentHistoryOptions {
  maxStackSize?: number
}

/**
 * Service for managing undo/redo history of document content (Angular port of React `useDocumentHistory`).
 * Maintains an immutable stack of snapshots with a movable pointer.
 *
 * Per-component state → `@Injectable()` without `providedIn`: list it in the consumer's `providers`
 * and call `init(initialContent, options)` once. `initialContent` may be a getter (e.g. a signal) —
 * React received it on every render and used the latest value as fallback for `content`/`markSaved`.
 */
@Injectable()
export class DocumentHistoryService {
  private maxStackSize = 100
  private initialContentFn: () => string = () => ''

  private readonly _stack = signal<string[]>([''])
  private readonly _pointer = signal(0)
  private readonly savedContent = signal('')

  readonly stack = this._stack.asReadonly()
  readonly pointer = this._pointer.asReadonly()
  readonly content = computed(() => this._stack()[this._pointer()] ?? this.initialContentFn())
  readonly canUndo = computed(() => this._pointer() > 0)
  readonly canRedo = computed(() => this._pointer() < this._stack().length - 1)
  readonly isDirty = computed(() => this.content() !== this.savedContent())

  /** Hook parameters (React `useDocumentHistory(initialContent, options)`). */
  init(initialContent: string | (() => string) = '', options: DocumentHistoryOptions = {}): void {
    this.initialContentFn = typeof initialContent === 'function' ? initialContent : () => initialContent
    this.maxStackSize = options.maxStackSize ?? 100
    const initial = untracked(() => this.initialContentFn())
    this._stack.set([initial])
    this._pointer.set(0)
    this.savedContent.set(initial)
  }

  /**
   * Push a new content snapshot. Trims any redo history past the current pointer.
   */
  pushContent = (newContent: string): void => {
    const pointer = this._pointer()
    const maxStackSize = this.maxStackSize
    this._stack.update((prev) => {
      const trimmed = prev.slice(0, pointer + 1)
      const next = [...trimmed, newContent]
      // Enforce max stack size
      if (next.length > maxStackSize) {
        next.shift()
        return next
      }
      return next
    })
    this._pointer.update((prev) => Math.min(prev + 1, maxStackSize - 1))
  }

  undo = (): void => {
    this._pointer.update((prev) => Math.max(0, prev - 1))
  }

  redo = (): void => {
    const stackLength = this._stack().length
    this._pointer.update((prev) => Math.min(stackLength - 1, prev + 1))
  }

  /**
   * Mark the current content as "saved" so isDirty resets.
   */
  markSaved = (): void => {
    this.savedContent.set(this._stack()[this._pointer()] ?? this.initialContentFn())
  }

  /**
   * Reset the entire history to a new initial value (e.g., loading a new conversation).
   */
  resetHistory = (content: string): void => {
    this._stack.set([content])
    this._pointer.set(0)
    this.savedContent.set(content)
  }
}
