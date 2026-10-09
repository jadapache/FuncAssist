import { API_BASE, handleResponse } from '../../../api/client'

export type MediaMetadata = {
  title: string
  description?: string
  size_bytes?: number
  file_size_formatted?: string
}

export type TranscriptionSegment = {
  start: number
  end: number
  speaker: string
  text: string
}

export type TranscriptionSummary = {
  summary_text?: string
  key_insights?: string[]
  participants?: string[]
  topics?: string[]
  decisions?: string[]
  requirements?: string[]
  action_items?: string[]
}

export type TranscriptionProgress = {
  id: string
  media_id: string
  title?: string | null
  status: 'pending' | 'uploading' | 'preprocessing' | 'transcribing' | 'diarizing' | 'summarizing' | 'complete' | 'failed' | 'cancelled'
  stage?: string
  progress: number
  message: string
  preview?: string | null
  eta?: string | null
  model_info?: string | null
  error?: string | null
  timestamp?: string | null
  live_segments?: TranscriptionSegment[]
  live_text?: string | null
}

export type TranscriptionResult = {
  id: string
  media_id: string
  metadata: MediaMetadata
  language: string
  duration_seconds: number
  created_at: string
  segments: TranscriptionSegment[]
  text: string
  summary?: TranscriptionSummary | null
  saved_to_knowledge?: boolean
  document_id?: string | null
}

export type TranscribeOptions = {
  transcription_id?: string
  mode?: 'auto' | 'local' | 'cloud' | 'groq' | 'openai'
  language?: string
  model_size?: string
  enable_diarization?: boolean
}

export type AvailableModelsInfo = {
  configured_provider: string
  configured_model: string
  local_available: boolean
  groq_configured: boolean
  openai_configured: boolean
  available_providers: string[]
  active_model_label: string
}

export const transcriptionApi = {
  getProgressStreamUrl(transcriptionId: string): string {
    return `${API_BASE}/api/transcription/progress-stream/${transcriptionId}`
  },

  async getAvailableModels(): Promise<AvailableModelsInfo> {
    const response = await fetch(`${API_BASE}/api/transcription/available-models`)
    return handleResponse(response)
  },

  async pickLocalFile(): Promise<{
    ok: boolean
    selected?: boolean
    cancelled?: boolean
    path?: string
    filename?: string
    size_bytes?: number
    size_formatted?: string
    is_video?: boolean
    error?: string
  }> {
    const response = await fetch(`${API_BASE}/api/transcription/pick-local-file`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    return handleResponse(response)
  },

  async inspectFile(filePath: string): Promise<{
    ok: boolean
    exists?: boolean
    path?: string
    filename?: string
    size_bytes?: number
    size_formatted?: string
    is_video?: boolean
    error?: string
  }> {
    const response = await fetch(`${API_BASE}/api/transcription/inspect-file`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ file_path: filePath }),
    })
    return handleResponse(response)
  },

  async registerLocalPath(
    localPath: string,
    title: string,
    description: string = '',
    transcriptionId?: string
  ): Promise<{ ok: boolean; media_id: string; transcription_id: string; size: number; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/register-local-path`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        local_path: localPath,
        title,
        description,
        transcription_id: transcriptionId,
      }),
    })
    return handleResponse(response)
  },

  async startTranscription(mediaId: string, options?: TranscribeOptions): Promise<{ ok: boolean; status: string; transcription_id: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/transcribe/${mediaId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(options || {}),
    })
    return handleResponse(response)
  },

  async retranscribe(transcriptionId: string, options?: TranscribeOptions): Promise<{ ok: boolean; status: string; transcription_id: string; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/retranscribe/${transcriptionId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(options || {}),
    })
    return handleResponse(response)
  },

  async getTranscriptionStatus(transcriptionId: string): Promise<TranscriptionProgress> {
    const response = await fetch(`${API_BASE}/api/transcription/status/${transcriptionId}`)
    return handleResponse(response)
  },

  async cancelTranscription(transcriptionId: string): Promise<{ ok: boolean; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/cancel/${transcriptionId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    return handleResponse(response)
  },

  async getTranscriptionResult(transcriptionId: string): Promise<TranscriptionResult> {
    const response = await fetch(`${API_BASE}/api/transcription/result/${transcriptionId}`)
    return handleResponse(response)
  },

  async generateSummary(transcriptionId: string): Promise<{ ok: boolean; summary: TranscriptionSummary; transcription: TranscriptionResult }> {
    const response = await fetch(`${API_BASE}/api/transcription/generate-summary/${transcriptionId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    return handleResponse(response)
  },

  async updateTranscriptionSummary(transcriptionId: string, summary: TranscriptionSummary): Promise<{ ok: boolean; transcription: TranscriptionResult }> {
    const response = await fetch(`${API_BASE}/api/transcription/summary/${transcriptionId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ summary }),
    })
    return handleResponse(response)
  },

  async renameSpeakers(transcriptionId: string, speakerMap: Record<string, string>): Promise<{ ok: boolean; transcription: TranscriptionResult }> {
    const response = await fetch(`${API_BASE}/api/transcription/speakers/${transcriptionId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ speaker_map: speakerMap }),
    })
    return handleResponse(response)
  },

  async saveToKnowledgeBase(transcriptionId: string, customTags: string[] = []): Promise<{ ok: boolean; document_id: string; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/save-to-knowledge/${transcriptionId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ custom_tags: customTags }),
    })
    return handleResponse(response)
  },

  async listTranscriptions(): Promise<{ transcriptions: TranscriptionResult[] }> {
    const response = await fetch(`${API_BASE}/api/transcription/list`)
    return handleResponse(response)
  },

  async deleteTranscription(transcriptionId: string): Promise<{ ok: boolean; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/${transcriptionId}`, {
      method: 'DELETE',
    })
    return handleResponse(response)
  },

  async exportInventarioXlsx(content: string, title: string = 'Inventario_de_Requerimientos'): Promise<Blob> {
    const response = await fetch(`${API_BASE}/api/transcription/export/inventario`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content, title }),
    })
    if (!response.ok) {
      throw new Error(`Error al exportar Inventario XLSX (${response.status})`)
    }
    return response.blob()
  },

  async exportLevantamientoDocx(content: string, title: string = 'Levantamiento_Detallado'): Promise<Blob> {
    const response = await fetch(`${API_BASE}/api/transcription/export/levantamiento`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content, title }),
    })
    if (!response.ok) {
      throw new Error(`Error al exportar Levantamiento DOCX (${response.status})`)
    }
    return response.blob()
  },
}
