declare module '@huggingface/transformers' {
  export const pipeline: (task: string, model: string, options?: Record<string, unknown>) => Promise<unknown>
  export const env: Record<string, unknown>

  /** `from_pretrained` loaders used by the in-browser speaker diarization (workers/diarizer.ts). */
  export interface PretrainedLoader {
    from_pretrained: (modelId: string, options?: Record<string, unknown>) => Promise<unknown>
  }
  export const AutoModel: PretrainedLoader
  export const AutoModelForAudioFrameClassification: PretrainedLoader
  export const AutoProcessor: PretrainedLoader
}
