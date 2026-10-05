import React, { useState, useRef } from 'react'
import {
  Upload,
  FileAudio,
  FileVideo,
  X,
  Sparkles,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'

interface UploadAreaProps {
  onUpload: (file: File, title: string, description?: string) => Promise<void>
  isUploading?: boolean
  configuredModelLabel?: string
}

const SUPPORTED_EXTS = ['.mp3', '.mp4', '.wav', '.m4a', '.webm', '.ogg', '.flac', '.aac', '.opus', '.mkv', '.mov']
const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024 // 2 GB

export const UploadArea: React.FC<UploadAreaProps> = ({
  onUpload,
  isUploading = false,
  configuredModelLabel,
}) => {
  const [dragActive, setDragActive] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const cleanTitleFromFilename = (filename: string): string => {
    const base = filename.replace(/\.[^/.]+$/, '')
    return base
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

  const handleFile = (file: File) => {
    setValidationError(null)
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!SUPPORTED_EXTS.includes(ext)) {
      setValidationError(`Formato '${ext}' no admitido. Formatos válidos: MP3, WAV, M4A, MP4, WebM, OGG, FLAC.`)
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      setValidationError('El archivo supera el tamaño máximo permitido de 2GB.')
      return
    }

    setSelectedFile(file)
    if (!title.trim()) {
      setTitle(cleanTitleFromFilename(file.name))
    }
  }

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0])
    }
  }

  const handleClear = () => {
    setSelectedFile(null)
    setTitle('')
    setDescription('')
    setValidationError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return
    const finalTitle = title.trim() || cleanTitleFromFilename(selectedFile.name)
    await onUpload(selectedFile, finalTitle, description)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  const isVideo = selectedFile?.type.startsWith('video/') || selectedFile?.name.match(/\.(mp4|webm|mkv|mov|avi)$/i)

  return (
    <div className="card p-6 bg-white border border-slate-200 shadow-sm rounded-2xl space-y-5">
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Drag & Drop Area */}
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !selectedFile && fileInputRef.current?.click()}
          className={`relative rounded-2xl border-2 border-dashed p-8 transition flex flex-col items-center justify-center text-center cursor-pointer ${
            dragActive
              ? 'border-blue-500 bg-blue-50/70 shadow-md ring-4 ring-blue-500/10'
              : selectedFile
              ? 'border-emerald-300 bg-emerald-50/30'
              : 'border-slate-300 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/30'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,video/*,.mp3,.mp4,.wav,.m4a,.webm,.ogg,.flac,.aac,.opus,.mkv,.mov"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            className="hidden"
          />

          {!selectedFile ? (
            <div className="space-y-3.5">
              <div className="flex h-14 w-14 mx-auto items-center justify-center rounded-2xl bg-blue-50 text-[#002777] shadow-inner ring-1 ring-blue-100 group-hover:scale-105 transition-transform">
                <Upload className="h-7 w-7" />
              </div>
              <div>
                <p className="text-base font-bold text-slate-800">
                  Arrastra tu grabación aquí o haz clic para explorar
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Audio o video (MP3, WAV, M4A, MP4, WebM, FLAC) hasta 2 GB
                </p>
              </div>
            </div>
          ) : (
            <div className="w-full flex items-center justify-between gap-4 p-2">
              <div className="flex items-center gap-3.5 text-left min-w-0">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 shadow-xs">
                  {isVideo ? <FileVideo className="h-6 w-6" /> : <FileAudio className="h-6 w-6" />}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-slate-900 truncate">
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-2">
                    <span>{formatFileSize(selectedFile.size)}</span>
                    <span>•</span>
                    <span className="text-emerald-700 font-semibold flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Archivo listo
                    </span>
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  handleClear()
                }}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 rounded-xl transition"
                title="Quitar archivo"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          )}
        </div>

        {/* Validation Error Alert */}
        {validationError && (
          <div className="flex items-center gap-2.5 p-3 rounded-xl bg-red-50 text-red-700 text-xs border border-red-200 animate-fade-in">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{validationError}</span>
          </div>
        )}

        {/* Meeting Metadata Fields (Visible once file is selected) */}
        {selectedFile && (
          <div className="space-y-4 pt-1 animate-fade-in">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                Título de la Reunión <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ej. Kickoff Proyecto Pagos QR - Sprint 1"
                required
                className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777] transition"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                Descripción o Contexto Adicional <span className="text-slate-400 font-normal">(Opcional)</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Notas de contexto, stakeholders clave o especificaciones preliminares..."
                rows={2}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777] transition"
              />
            </div>

            {/* Model & Setting Indicator */}
            {configuredModelLabel && (
              <div className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-blue-50/70 border border-blue-100 text-xs text-slate-600">
                <span className="flex items-center gap-1.5 text-slate-700">
                  <Sparkles className="h-3.5 w-3.5 text-[#002777]" />
                  <span>Motor configurado en Ajustes:</span>
                </span>
                <span className="font-bold text-[#002777]">{configuredModelLabel}</span>
              </div>
            )}

            {/* Submit CTA */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={handleClear}
                disabled={isUploading}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                Cancelar
              </button>

              <button
                type="submit"
                disabled={isUploading || !title.trim()}
                className="btn-primary px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 text-xs shadow-md shadow-blue-900/10"
              >
                {isUploading ? (
                  <>
                    <Sparkles className="h-4 w-4 animate-spin" />
                    <span>Iniciando Transcripción...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    <span>Iniciar Transcripción & Análisis</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </form>
    </div>
  )
}
