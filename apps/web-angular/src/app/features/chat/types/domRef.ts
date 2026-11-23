/**
 * Minimal equivalent of a React `RefObject<T>`.
 * The chat components share DOM nodes across component boundaries exactly like the React
 * props did (`textareaRef`, `fileInputRef`, `chatBottomRef`): the owner creates the object and
 * the component that renders the element assigns `current`.
 */
export interface DomRef<T> {
  current: T | null
}

export function createDomRef<T>(): DomRef<T> {
  return { current: null }
}
