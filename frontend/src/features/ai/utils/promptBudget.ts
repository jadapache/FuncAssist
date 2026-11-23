/**
 * Keeps prompts for in-browser models inside their context window.
 *
 * WebLLM loads the catalog models with a 4,096-token context (the VRAM figures assume that size).
 * Longer prompts either fail or, on weak GPUs, make a single prefill take so long that Windows
 * resets the GPU. Prompts are trimmed in the middle of the longest message so that both the
 * instructions at the start and the question at the end survive.
 */
import type { ChatMessage } from '../types/webLlm'

/** Context window WebLLM uses for the prebuilt catalog models (prebuiltAppConfig overrides). */
export const BROWSER_CONTEXT_TOKENS = 4096
/** Conservative characters-per-token for Spanish text without the real tokenizer. */
export const CHARS_PER_TOKEN = 3.2
const PER_MESSAGE_OVERHEAD = 8
const SAFETY_MARGIN = 64
const MIN_OUTPUT_TOKENS = 256
const DEFAULT_OUTPUT_TOKENS = 1536
export const TRIM_MARKER = '\n\n[… contenido recortado para el modelo del navegador …]\n\n'

export function estimateTokens(text: string, charsPerToken = CHARS_PER_TOKEN): number {
  return Math.ceil((text || '').length / charsPerToken)
}

export function estimatePromptTokens(messages: ChatMessage[], charsPerToken = CHARS_PER_TOKEN): number {
  return messages.reduce((total, m) => total + estimateTokens(m.content, charsPerToken) + PER_MESSAGE_OVERHEAD, 0)
}

/** Output tokens to reserve: what was asked for, but never more than half of the window. */
export function outputReserve(contextTokens: number, requested?: number): number {
  const wanted = requested ?? DEFAULT_OUTPUT_TOKENS
  return Math.max(MIN_OUTPUT_TOKENS, Math.min(wanted, Math.floor(contextTokens / 2)))
}

function trimMiddle(text: string, keepChars: number): string {
  if (text.length <= keepChars) return text
  const usable = Math.max(0, keepChars - TRIM_MARKER.length)
  const head = Math.ceil(usable * 0.6)
  const tail = usable - head
  return `${text.slice(0, head)}${TRIM_MARKER}${tail > 0 ? text.slice(text.length - tail) : ''}`
}

export interface FittedPrompt {
  messages: ChatMessage[]
  trimmed: boolean
  promptTokens: number
  maxTokens: number
}

/**
 * Fits the messages and the output budget into the context window. The longest message is
 * trimmed first (usually the document or transcript), repeatedly, until everything fits.
 */
export function fitPromptToContext(
  messages: ChatMessage[],
  contextTokens: number = BROWSER_CONTEXT_TOKENS,
  requestedOutput?: number,
  charsPerToken: number = CHARS_PER_TOKEN,
): FittedPrompt {
  const reserve = outputReserve(contextTokens, requestedOutput)
  const inputBudget = Math.max(256, contextTokens - reserve - SAFETY_MARGIN)
  const fitted = messages.map((m) => ({ ...m }))
  let trimmed = false

  for (let guard = 0; guard < 8; guard++) {
    const total = estimatePromptTokens(fitted, charsPerToken)
    if (total <= inputBudget) break
    let longest = 0
    for (let i = 1; i < fitted.length; i++) {
      if (fitted[i].content.length > fitted[longest].content.length) longest = i
    }
    const excessChars = Math.ceil((total - inputBudget) * charsPerToken)
    const current = fitted[longest].content
    const target = Math.max(200, current.length - excessChars - TRIM_MARKER.length)
    if (target >= current.length) break
    fitted[longest] = { ...fitted[longest], content: trimMiddle(current, target) }
    trimmed = true
  }

  const promptTokens = estimatePromptTokens(fitted, charsPerToken)
  const room = contextTokens - promptTokens - SAFETY_MARGIN
  const maxTokens = Math.max(MIN_OUTPUT_TOKENS, Math.min(reserve, room))
  return { messages: fitted, trimmed, promptTokens, maxTokens }
}
