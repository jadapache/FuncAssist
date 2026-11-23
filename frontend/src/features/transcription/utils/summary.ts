import { api } from '../../../api/client'
import { inferenceService } from '../../ai/services/InferenceService'
import { transcriptionApi, type TranscriptionResult } from '../api/transcriptionApi'
import { condenseTranscriptForBrowser, formatTranscriptForPrompt } from './transcriptFormat'

export const DEFAULT_SUMMARY_TEMPLATE = 'transcript_summary_standard_meeting'

const DEFAULT_SYSTEM_PROMPT =
  'Eres un analista y redactor ejecutivo senior especializado en minutas y notas de reunión. Genera una síntesis profesional, clara y estructurada de la reunión basada estrictamente en la transcripción. No inventes información que no esté sustentada en la grabación.'
const DEFAULT_USER_TEMPLATE = 'Título de la reunión: {title}\n\nTRANSCRIPCIÓN:\n{transcript}\n\nRÚBRICA:\n{rubric}'
const BROWSER_TRANSCRIPT_BUDGET = 8000

export interface GenerateSummaryArgs {
  transcriptionId: string
  title: string
  templateId?: string
  templateTitle?: string
  /** Transcript already loaded; fetched when absent and the browser model is used. */
  record?: TranscriptionResult | null
}

/**
 * The only summary entry point of the feature. With a cloud writing provider the backend
 * generates and stores it; with WebLLM it is generated here (clean text, grouped in turns) and
 * stored with `PUT /summary`. Returns the updated transcription.
 */
export async function generateTranscriptSummary(args: GenerateSummaryArgs): Promise<TranscriptionResult> {
  const templateId = args.templateId?.trim() || DEFAULT_SUMMARY_TEMPLATE
  const settings = await inferenceService.getAiSettings()

  if (!inferenceService.isBrowserExecution(settings)) {
    const response = await transcriptionApi.generateSummary(args.transcriptionId, templateId)
    return response.transcription
  }

  const record = args.record ?? (await transcriptionApi.getTranscriptionResult(args.transcriptionId))
  const transcript = formatTranscriptForPrompt(record, 'clean')
  if (!transcript) throw new Error('La transcripción no tiene diálogos que resumir.')

  const [prompt, rubric] = await Promise.all([
    api.getAiPrompt(templateId).catch(() => null),
    api.getAiRubric(templateId).catch(() => null),
  ])
  const rubricText = rubric?.criteria?.length ? rubric.criteria.map((criterion) => `- ${criterion}`).join('\n') : ''
  const systemPrompt = prompt?.system?.trim() || DEFAULT_SYSTEM_PROMPT
  const userTemplate = prompt?.user_template?.trim() || DEFAULT_USER_TEMPLATE
  const userContent = userTemplate
    .replace('{title}', args.title || 'Reunión')
    .replace('{transcript}', condenseTranscriptForBrowser(transcript, BROWSER_TRANSCRIPT_BUDGET))
    .replace('{rubric}', rubricText)

  const generated = await inferenceService.generateMessages(
    [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userContent },
    ],
    undefined,
    { temperature: 0.3, maxTokens: 2500 },
  )

  const promptTitle = typeof prompt?.title === 'string' ? prompt.title : undefined
  const updated = await transcriptionApi.updateTranscriptionSummary(args.transcriptionId, {
    summary_text: generated.content,
    template_id: templateId,
    template_name: args.templateTitle || promptTitle || templateId,
  })
  return updated.transcription
}
