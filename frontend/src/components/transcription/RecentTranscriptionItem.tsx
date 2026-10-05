import type React from 'react'
import {
  FileText,
  Calendar,
  Clock,
  HardDrive,
  Trash2,
} from 'lucide-react'
import type { TranscriptionResult } from '../../api/modules/transcription'

interface RecentTranscriptionItemProps {
  transcription: TranscriptionResult
  viewMode?: 'grid' | 'list'
  onOpenSummary: (transcriptionId: string) => void
  onRequestDelete: (transcription: TranscriptionResult) => void
}

function formatSeconds(seconds: number): string {
  if (!seconds || isNaN(seconds) || seconds <= 0) return '0 s'
  return `${Math.round(seconds)} s`
}

function formatFileSize(transcription: TranscriptionResult): string {
  if (transcription.metadata?.file_size_formatted && transcription.metadata.file_size_formatted !== 'Audio') {
    return transcription.metadata.file_size_formatted
  }
  const bytes = transcription.metadata?.size_bytes
  if (typeof bytes === 'number' && bytes > 35) {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${bytes} B`
  }
  // Approximate audio size based on duration (~128 kbps = ~16 KB/sec)
  if (transcription.duration_seconds && transcription.duration_seconds > 0) {
    const approx = Math.round(transcription.duration_seconds * 16000)
    if (approx >= 1024 * 1024) return `${(approx / (1024 * 1024)).toFixed(1)} MB`
    return `${Math.round(approx / 1024)} KB`
  }
  return '1.5 MB'
}

function formatDateTime(isoString: string): string {
  try {
    const d = new Date(isoString)
    return d.toLocaleDateString('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoString || 'Reciente'
  }
}

export const RecentTranscriptionItem: React.FC<RecentTranscriptionItemProps> = ({
  transcription,
  viewMode = 'grid',
  onOpenSummary,
  onRequestDelete,
}) => {
  const title = transcription.metadata?.title || 'Transcripción de Reunión'
  const description = transcription.metadata?.description || 'Sin descripción adicional.'
  const sizeStr = formatFileSize(transcription)
  const durationStr = formatSeconds(transcription.duration_seconds)
  const dateTimeStr = formatDateTime(transcription.created_at)

  if (viewMode === 'list') {
    return (
      <div
        onClick={() => onOpenSummary(transcription.id)}
        className="group relative p-4 bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50/20 rounded-2xl shadow-2xs transition-all duration-150 hover:shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer"
      >
        <div className="flex items-start sm:items-center gap-3.5 min-w-0 flex-1">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-[#002777] ring-1 ring-blue-100 group-hover:scale-105 transition">
            <FileText className="h-5 w-5" />
          </div>

          <div className="min-w-0 flex-1 space-y-0.5">
            <h4 className="text-sm font-bold text-slate-900 group-hover:text-[#002777] transition truncate" title={title}>
              {title}
            </h4>
            <p className="text-xs text-slate-500 line-clamp-1" title={description}>
              {description}
            </p>
            <div className="flex flex-wrap items-center gap-2.5 text-[11px] text-slate-400 pt-1">
              <span className="flex items-center gap-1 font-medium text-slate-600">
                <Calendar className="h-3 w-3 text-slate-400 shrink-0" />
                <span>{dateTimeStr}</span>
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 font-medium text-slate-600">
                <Clock className="h-3 w-3 text-slate-400 shrink-0" />
                <span>{durationStr}</span>
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 font-medium text-slate-600">
                <HardDrive className="h-3 w-3 text-slate-400 shrink-0" />
                <span>{sizeStr}</span>
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onRequestDelete(transcription)
            }}
            className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-xl border border-transparent hover:border-red-200 transition cursor-pointer"
            title="Eliminar transcripción"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    )
  }

  // Grid Mode (Card)
  return (
    <div
      onClick={() => onOpenSummary(transcription.id)}
      className="group relative p-5 bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50/20 rounded-2xl shadow-xs transition-all duration-200 hover:shadow-md flex flex-col justify-between space-y-4 cursor-pointer"
    >
      <div className="space-y-3">
        {/* Header with Icon, Title, and Delete Button on top-right */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3.5 min-w-0 flex-1">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-[#002777] ring-1 ring-blue-100 shadow-xs group-hover:scale-105 transition">
              <FileText className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1 space-y-0.5 pr-2">
              <h4 className="text-sm font-bold text-slate-900 group-hover:text-[#002777] transition truncate" title={title}>
                {title}
              </h4>
              <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed" title={description}>
                {description}
              </p>
            </div>
          </div>

          {/* Delete Button on Top Right */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onRequestDelete(transcription)
            }}
            className="p-1.5 -mr-1.5 -mt-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition cursor-pointer shrink-0"
            title="Eliminar transcripción"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>

        {/* Metadata Details: Los 3 metadatos alineados en una sola fila */}
        <div className="flex flex-wrap items-center gap-2.5 text-[11px] text-slate-400 pt-3 border-t border-slate-100">
          <span className="flex items-center gap-1 font-medium text-slate-600">
            <Calendar className="h-3 w-3 text-slate-400 shrink-0" />
            <span>{dateTimeStr}</span>
          </span>
          <span>•</span>
          <span className="flex items-center gap-1 font-medium text-slate-600">
            <Clock className="h-3 w-3 text-slate-400 shrink-0" />
            <span>{durationStr}</span>
          </span>
          <span>•</span>
          <span className="flex items-center gap-1 font-medium text-slate-600">
            <HardDrive className="h-3 w-3 text-slate-400 shrink-0" />
            <span>{sizeStr}</span>
          </span>
        </div>
      </div>
    </div>
  )
}

