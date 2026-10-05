import { API_BASE, getAuthHeaders, handleResponse } from '../client'

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
  status: 'pending' | 'uploading' | 'preprocessing' | 'transcribing' | 'diarizing' | 'summarizing' | 'complete' | 'failed' | 'cancelled'
  stage?: string
  progress: number
  message: string
  preview?: string | null
  eta?: string | null
  model_info?: string | null
  error?: string | null
  timestamp?: string | null
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

/**
 * Upload media file with XMLHttpRequest to track real-time upload progress.
 */
export function uploadMediaWithProgress(
  file: File,
  title: string,
  description: string = '',
  onProgress?: (progress: number, message: string) => void
): Promise<{ ok: boolean; media_id: string; transcription_id: string; size: number; message: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const fileSize = file.size || 1

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        const bytesReceived = event.loaded
        const uploadProgress = Math.min(100, Math.round((bytesReceived / fileSize) * 100))
        const mbReceived = (bytesReceived / 1024 / 1024).toFixed(1)
        const mbTotal = (fileSize / 1024 / 1024).toFixed(1)
        const message = `Subiendo archivo... ${mbReceived}MB / ${mbTotal}MB`
        onProgress?.(uploadProgress, message)
      }
    })

    xhr.upload.addEventListener('loadstart', () => {
      onProgress?.(0, 'Iniciando subida de archivo...')
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText)
          onProgress?.(100, 'Subida completada con éxito')
          resolve(response)
        } catch {
          reject(new Error('Respuesta del servidor no válida'))
        }
      } else {
        try {
          const errJson = JSON.parse(xhr.responseText)
          reject(new Error(errJson.detail || `Error al subir archivo (${xhr.status})`))
        } catch {
          reject(new Error(`Error al subir archivo (${xhr.status})`))
        }
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error('Error de red durante la subida del archivo'))
    })

    xhr.addEventListener('abort', () => {
      reject(new Error('Subida cancelada por el usuario'))
    })

    xhr.timeout = 10 * 60 * 1000 // 10 minutes timeout for large recordings
    xhr.addEventListener('timeout', () => {
      reject(new Error('Tiempo de espera agotado al subir el archivo'))
    })

    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', title)
    formData.append('description', description)

    const token = localStorage.getItem('auth_token')
    xhr.open('POST', `${API_BASE}/api/transcription/upload-stream`, true)
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    xhr.send(formData)
  })
}

export const transcriptionApi = {
  uploadMediaWithProgress,

  getProgressStreamUrl(transcriptionId: string): string {
    return `${API_BASE}/api/transcription/progress-stream/${transcriptionId}`
  },

  async getAvailableModels(): Promise<AvailableModelsInfo> {
    const response = await fetch(`${API_BASE}/api/transcription/available-models`, {
      headers: getAuthHeaders(),
    })
    return handleResponse(response)
  },

  async uploadMedia(file: File, title: string, description: string = ''): Promise<{ ok: boolean; media_id: string; transcription_id?: string; message: string }> {
    return uploadMediaWithProgress(file, title, description)
  },

  async startTranscription(mediaId: string, options?: TranscribeOptions): Promise<{ ok: boolean; status: string; transcription_id: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/transcribe/${mediaId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify(options || {}),
    })
    return handleResponse(response)
  },

  async getTranscriptionStatus(transcriptionId: string): Promise<TranscriptionProgress> {
    const response = await fetch(`${API_BASE}/api/transcription/status/${transcriptionId}`, {
      headers: getAuthHeaders(),
    })
    return handleResponse(response)
  },

  async cancelTranscription(transcriptionId: string): Promise<{ ok: boolean; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/cancel/${transcriptionId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
    })
    return handleResponse(response)
  },

  async getTranscriptionResult(transcriptionId: string): Promise<TranscriptionResult> {
    const response = await fetch(`${API_BASE}/api/transcription/result/${transcriptionId}`, {
      headers: getAuthHeaders(),
    })
    return handleResponse(response)
  },

  async generateSummary(transcriptionId: string): Promise<{ ok: boolean; summary: TranscriptionSummary; transcription: TranscriptionResult }> {
    const response = await fetch(`${API_BASE}/api/transcription/generate-summary/${transcriptionId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
    })
    return handleResponse(response)
  },

  async updateTranscriptionSummary(transcriptionId: string, summary: TranscriptionSummary): Promise<{ ok: boolean; transcription: TranscriptionResult }> {
    const response = await fetch(`${API_BASE}/api/transcription/summary/${transcriptionId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
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
        ...getAuthHeaders(),
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
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ custom_tags: customTags }),
    })
    return handleResponse(response)
  },

  async listTranscriptions(): Promise<{ transcriptions: TranscriptionResult[] }> {
    const response = await fetch(`${API_BASE}/api/transcription/list`, {
      headers: getAuthHeaders(),
    })
    return handleResponse(response)
  },

  async deleteTranscription(transcriptionId: string): Promise<{ ok: boolean; message: string }> {
    const response = await fetch(`${API_BASE}/api/transcription/${transcriptionId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    return handleResponse(response)
  },

  async exportInventarioXlsx(content: string, title: string = 'Inventario_de_Requerimientos'): Promise<Blob> {
    const response = await fetch(`${API_BASE}/api/transcription/export/inventario`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
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
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ content, title }),
    })
    if (!response.ok) {
      throw new Error(`Error al exportar Levantamiento DOCX (${response.status})`)
    }
    return response.blob()
  },
}
