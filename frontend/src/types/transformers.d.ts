declare module '@huggingface/transformers' {
  export const pipeline: (task: string, model: string, options?: Record<string, unknown>) => Promise<unknown>
  export const env: Record<string, unknown>
}
