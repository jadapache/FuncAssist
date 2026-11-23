import { API_BASE, getAuthHeaders } from '../../../core/api/config'
import { handleResponse } from '../../../api/client'
import { abortError } from '../utils/abort'

export { isAbortError } from '../utils/abort'

export type MediaMetadata = {
  title: string
  description?: string
  size_bytes?: number
  file_size_formatted?: string
}

export type TranscriptionSegment = {
  /** Stable id assigned by the backend (`seg_0001`). Absent only in live, not yet saved segments. */
  id?: string
  start: number
  end: number
  /** Display name, derived from `speakers[speaker_id].name`. */
  speaker: string
  speaker_id?: string
  /** Clean text (fillers removed). Manual edits apply here. */
  text: string
  /** Verbatim provider output. */
  text_raw?: string
  tags?: string[]
  marked?: boolean
}

export type SpeakerInfo = {
  name: string
  color_index: number
}

export type TranscriptionSummary = {
  summary_text?: string
  key_insights?: string[]
  participants?: string[]
  topics?: string[]
  decisions?: string[]
  requirements?: string[]
  action_items?: string[]
  template_id?: string
  template_name?: string
}

export type SummaryTemplateItem = {
  id: string
  title: string
  description?: string
  tag?: string
}

/** Stages of the progress contract (docs/TRANSCRIPTION_PROCESS.md §3). */
export type ServerStage =
  | 'uploading'
  | 'queued'
  | 'preprocessing'
  | 'transcribing'
  | 'cleaning'
  | 'diarizing'
  | 'saving'
  | 'complete'
  | 'failed'
  | 'cancelled'
  | 'interrupted'

/** Stages that only exist for in-browser jobs. */
export type BrowserStage = 'decoding' | 'model_download'

export type TranscriptionStage = ServerStage | BrowserStage

export type SummaryStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

export type TranscriptionProgress = {
  id: string
  media_id?: string
  title?: string | null
  /** Same value as `stage` (kept by the backend for compatibility). */
  status?: string
  stage: TranscriptionStage
  /** 0..1 within the current stage. */
  stage_progress?: number | null
  /** 0..100, monotonic. */
  progress: number
  message?: string
  eta?: string | null
  eta_seconds?: number | null
  chunks_done?: number | null
  chunks_total?: number | null
  queue_position?: number | null
  error?: string | null
  error_code?: string | null
  retryable?: boolean
  summary_status?: SummaryStatus | null
  model_info?: string | null
  seq?: number | null
  timestamp?: string | null
}

export type TranscriptionCleanupInfo = {
  mode?: string
  fillers_removed?: number
  hallucinations_removed?: number
}

export type TranscriptionResult = {
  id: string
  slug?: string | null
  media_id?: string
  metadata: MediaMetadata
  language: string
  duration_seconds: number
  created_at: string
  segments: TranscriptionSegment[]
  text: string
  summary?: TranscriptionSummary | null
  saved_to_knowledge?: boolean
  document_id?: string | null
  status?: string
  error?: string | null
  error_code?: string | null
  source?: 'cloud' | 'browser'
  /** The media is stored on the server, so the transcription can be regenerated. */
  has_media?: boolean
  diarization?: string
  speakers?: Record<string, SpeakerInfo>
  turn_gap_s?: number
  cleanup?: TranscriptionCleanupInfo | null
  silence_trimmed_s?: number | null
  summary_status?: SummaryStatus | null
  model_info?: string | null
}

export type CleanupMode = 'off' | 'rules' | 'llm'

export type TranscribeOptions = {
  transcription_id?: string
  language?: string
  diarize?: boolean
  num_speakers?: number
  vocabulary?: string
  cleanup?: CleanupMode
}

export type AvailableModelsInfo = {
  configured_provider: string
  configured_model: string
  local_available: boolean
  groq_configured: boolean
  openai_configured: boolean
  available_providers: string[]
  active_model_label: string
  /** OpenAI diarization is possible for server jobs. */
  diarization_available?: boolean
  /** User default for identifying speakers in in-browser jobs. */
  browser_diarization?: boolean
}

export type StartTranscriptionResponse = {
  ok: boolean
  status: string
  transcription_id: string
  media_id?: string
}

export type UploadMediaResponse = {
  ok: boolean
  media_id: string
  transcription_id: string
  size: number
  message?: string
}

export type SpeakersPatch = {
  rename?: Record<string, string>
  merge?: Array<{ from: string; into: string }>
}

export type SegmentPatch = {
  speaker_id?: string
  new_speaker_name?: string
  text?: string
  marked?: boolean
}

export type TranscriptionMutationResponse = {
  ok: boolean
  transcription: TranscriptionResult
}

export type ClientTranscriptionPayload = {
  id: string
  title: string
  description?: string
  text: string
  segments: TranscriptionSegment[]
  duration_seconds: number
  language?: string
  generate_summary_now?: boolean
  /** "browser" when segment speaker ids come from in-browser diarization. */
  diarization?: 'browser' | 'none'
}

/** HTTP error carrying the response status (413, 404…). */
export class TranscriptionApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'TranscriptionApiError'
    this.status = status
  }
}

export function errorStatus(err: unknown): number | null {
  const status = (err as { status?: unknown } | null)?.status
  return typeof status === 'number' ? status : null
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (typeof item === 'object' && item !== null && 'msg' in item ? String((item as { msg: unknown }).msg) : ''))
      .filter(Boolean)
    if (parts.length) return parts.join('. ')
  }
  return fallback
}

export type UploadProgressOptions = {
  signal?: AbortSignal
  onProgress?: (loaded: number, total: number) => void
}

/** Multipart POST with upload progress and abort support (fetch has no upload progress). */
function xhrUpload<T>(url: string, form: FormData, options: UploadProgressOptions = {}): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (options.signal?.aborted) {
      reject(abortError('Subida cancelada por el usuario.'))
      return
    }

    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    for (const [key, value] of Object.entries(getAuthHeaders())) {
      xhr.setRequestHeader(key, value)
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded, event.total)
    }
    xhr.onload = () => {
      let body: unknown = null
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        body = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T)
        return
      }
      const detail = (body as { detail?: unknown } | null)?.detail
      const fallback =
        xhr.status === 413
          ? 'El archivo supera el tamaño máximo permitido por el servidor.'
          : `Error al subir el archivo (${xhr.status}).`
      reject(new TranscriptionApiError(detailToMessage(detail, fallback), xhr.status))
    }
    xhr.onerror = () => reject(new Error('Error de red al subir el archivo.'))
    xhr.onabort = () => reject(abortError('Subida cancelada por el usuario.'))

    options.signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

const jsonHeaders = (): Record<string, string> => ({
  'Content-Type': 'application/json',
  ...getAuthHeaders(),
})

const base = `${API_BASE}/api/transcription`

export const transcriptionApi = {
  /** SSE endpoint (protocol v2: named `progress` / `heartbeat` events). */
  getProgressStreamUrl(transcriptionId: string): string {
    return `${base}/progress-stream/${encodeURIComponent(transcriptionId)}?protocol=v2`
  },

  async getAvailableModels(): Promise<AvailableModelsInfo> {
    const response = await fetch(`${base}/available-models`, { headers: { ...getAuthHeaders() } })
    return handleResponse(response)
  },

  /** Server-side FFmpeg extraction to 16 kHz WAV, for files the browser cannot decode. */
  async extractAudioTrack(file: File, signal?: AbortSignal): Promise<Blob> {
    const formData = new FormData()
    formData.append('file', file, file.name)
    const response = await fetch(`${base}/extract-audio`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
      body: formData,
      signal,
    })
    if (!response.ok) {
      let detail: unknown = null
      try {
        detail = (await response.json())?.detail
      } catch {
        // ignore
      }
      throw new TranscriptionApiError(
        detailToMessage(detail, `Error al extraer audio (${response.status})`),
        response.status,
      )
    }
    return response.blob()
  },

  uploadMediaFile(
    file: File | Blob,
    title: string,
    description: string = '',
    transcriptionId?: string,
    filename: string = file instanceof File ? file.name : 'media.wav',
    options: UploadProgressOptions = {},
  ): Promise<UploadMediaResponse> {
    const formData = new FormData()
    formData.append('file', file, filename)
    formData.append('title', title)
    formData.append('description', description)
    if (transcriptionId) formData.append('transcription_id', transcriptionId)
    return xhrUpload<UploadMediaResponse>(`${base}/upload`, formData, options)
  },

  async startTranscription(mediaId: string, options: TranscribeOptions = {}): Promise<StartTranscriptionResponse> {
    const response = await fetch(`${base}/transcribe/${encodeURIComponent(mediaId)}`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(options),
    })
    return handleResponse(response)
  },

  /** Resumes a failed or interrupted job from its saved chunks. */
  async retryTranscription(transcriptionId: string): Promise<StartTranscriptionResponse> {
    const response = await fetch(`${base}/retry/${encodeURIComponent(transcriptionId)}`, {
      method: 'POST',
      headers: jsonHeaders(),
    })
    return handleResponse(response)
  },

  async getActiveTranscriptionJobs(): Promise<TranscriptionProgress[]> {
    const response = await fetch(`${base}/jobs/active`, { headers: { ...getAuthHeaders() } })
    const data = await handleResponse<{ jobs?: TranscriptionProgress[] }>(response)
    return data?.jobs || []
  },

  async getTranscriptionStatus(transcriptionId: string, signal?: AbortSignal): Promise<TranscriptionProgress> {
    const response = await fetch(`${base}/status/${encodeURIComponent(transcriptionId)}`, {
      headers: { ...getAuthHeaders() },
      signal,
    })
    return handleResponse(response)
  },

  async cancelTranscription(transcriptionId: string): Promise<{ ok: boolean; message?: string }> {
    const response = await fetch(`${base}/cancel/${encodeURIComponent(transcriptionId)}`, {
      method: 'POST',
      headers: jsonHeaders(),
    })
    return handleResponse(response)
  },

  async getTranscriptionResult(transcriptionId: string): Promise<TranscriptionResult> {
    const response = await fetch(`${base}/result/${encodeURIComponent(transcriptionId)}`, {
      headers: { ...getAuthHeaders() },
    })
    return handleResponse(response)
  },

  async getSummaryTemplates(tag: string = 'transcript_summary'): Promise<SummaryTemplateItem[]> {
    try {
      const response = await fetch(`${base}/summary-templates?tag=${encodeURIComponent(tag)}`, {
        headers: { ...getAuthHeaders() },
      })
      const data = await handleResponse<{ templates: SummaryTemplateItem[] }>(response)
      return data.templates || []
    } catch {
      return []
    }
  },

  async generateSummary(
    transcriptionId: string,
    feature?: string,
  ): Promise<{ ok: boolean; summary: TranscriptionSummary; transcription: TranscriptionResult }> {
    const validFeature =
      typeof feature === 'string' && feature.trim().length > 0 ? feature.trim() : 'transcript_summary_standard_meeting'
    const response = await fetch(`${base}/generate-summary/${encodeURIComponent(transcriptionId)}`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ feature: validFeature }),
    })
    return handleResponse(response)
  },

  async updateTranscriptionSummary(
    transcriptionId: string,
    summary: TranscriptionSummary,
  ): Promise<TranscriptionMutationResponse> {
    const response = await fetch(`${base}/summary/${encodeURIComponent(transcriptionId)}`, {
      method: 'PUT',
      headers: jsonHeaders(),
      body: JSON.stringify({ summary }),
    })
    return handleResponse(response)
  },

  async updateSpeakers(transcriptionId: string, patch: SpeakersPatch): Promise<TranscriptionMutationResponse> {
    const response = await fetch(`${base}/${encodeURIComponent(transcriptionId)}/speakers`, {
      method: 'PATCH',
      headers: jsonHeaders(),
      body: JSON.stringify(patch),
    })
    return handleResponse(response)
  },

  async updateSegment(
    transcriptionId: string,
    segmentId: string,
    patch: SegmentPatch,
  ): Promise<TranscriptionMutationResponse> {
    const response = await fetch(
      `${base}/${encodeURIComponent(transcriptionId)}/segments/${encodeURIComponent(segmentId)}`,
      { method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify(patch) },
    )
    return handleResponse(response)
  },

  async splitSegment(transcriptionId: string, segmentId: string, at: number): Promise<TranscriptionMutationResponse> {
    const response = await fetch(
      `${base}/${encodeURIComponent(transcriptionId)}/segments/${encodeURIComponent(segmentId)}/split`,
      { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ at }) },
    )
    return handleResponse(response)
  },

  async saveToKnowledgeBase(
    transcriptionId: string,
    customTags: string[] = [],
  ): Promise<{ ok: boolean; document_id: string; message: string }> {
    const response = await fetch(`${base}/save-to-knowledge/${encodeURIComponent(transcriptionId)}`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ custom_tags: customTags }),
    })
    return handleResponse(response)
  },

  async listTranscriptions(): Promise<{ transcriptions: TranscriptionResult[] }> {
    const response = await fetch(`${base}/list`, { headers: { ...getAuthHeaders() } })
    return handleResponse(response)
  },

  async deleteTranscription(transcriptionId: string): Promise<{ ok: boolean; message: string }> {
    const response = await fetch(`${base}/${encodeURIComponent(transcriptionId)}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    })
    return handleResponse(response)
  },

  async exportInventarioXlsx(content: string, title: string = 'Inventario_de_Requerimientos'): Promise<Blob> {
    const response = await fetch(`${base}/export/inventario`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ content, title }),
    })
    if (!response.ok) {
      throw new Error(`Error al exportar Inventario XLSX (${response.status})`)
    }
    return response.blob()
  },

  async exportLevantamientoDocx(content: string, title: string = 'Levantamiento_Detallado'): Promise<Blob> {
    const response = await fetch(`${base}/export/levantamiento`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ content, title }),
    })
    if (!response.ok) {
      throw new Error(`Error al exportar Levantamiento DOCX (${response.status})`)
    }
    return response.blob()
  },

  async submitClientTranscription(
    payload: ClientTranscriptionPayload,
  ): Promise<{ ok: boolean; transcription: TranscriptionResult; summary?: TranscriptionSummary | null }> {
    const response = await fetch(`${base}/submit-client-transcription`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ ...payload, generate_summary_now: payload.generate_summary_now ?? false }),
    })
    return handleResponse(response)
  },
}
