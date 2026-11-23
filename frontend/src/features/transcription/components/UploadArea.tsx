import React, { useState, useRef } from 'react'
import {
  Upload,
  FileAudio,
  FileVideo,
  X,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Sliders,
} from 'lucide-react'
import type { UploadJobOptions } from '../hooks/useTranscriptionJobRunners'

interface UploadAreaProps {
  onUpload: (file: File, title: string, description: string, options: UploadJobOptions) => Promise<void>
  isUploading?: boolean
  configuredModelLabel?: string
  /** Server transcription: the options include the vocabulary and OpenAI diarization. */
  showServerOptions?: boolean
  /** In-browser jobs: initial state of "identify speakers" (user setting). */
  browserDiarizationDefault?: boolean
}

const SUPPORTED_EXTS = ['.mp3', '.mp4', '.wav', '.m4a', '.webm', '.ogg', '.flac', '.aac', '.opus', '.mkv', '.mov', '.wmv', '.avi']
const MAX_SPEAKERS = 10

const cleanTitleFromFilename = (filename: string): string =>
  filename
    .replace(/\.[^/.]+$/, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

const formatFileSize = (bytes: number) => {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export const UploadArea: React.FC<UploadAreaProps> = ({
  onUpload,
  isUploading = false,
  configuredModelLabel,
  showServerOptions = false,
  browserDiarizationDefault = false,
}) => {
  const defaultDiarize = showServerOptions ? true : browserDiarizationDefault
  const [dragActive, setDragActive] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [diarize, setDiarize] = useState(defaultDiarize)
  const [numSpeakers, setNumSpeakers] = useState('')
  const [vocabulary, setVocabulary] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handlePickerClick = () => {
    if (isUploading || selectedFile) return
    setValidationError(null)
    fileInputRef.current?.click()
  }

  const handleFile = (file: File) => {
    setValidationError(null)
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
    if (!SUPPORTED_EXTS.includes(ext)) {
      setValidationError(`Formato '${ext}' no admitido. Formatos válidos: MP3, WAV, M4A, MP4, WebM, OGG, FLAC.`)
      return
    }
    if (file.size <= 0) {
      setValidationError('El archivo seleccionado está vacío.')
      return
    }
    setSelectedFile(file)
    if (!title.trim()) setTitle(cleanTitleFromFilename(file.name))
  }

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true)
    else if (e.type === 'dragleave') setDragActive(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  const handleClear = () => {
    setSelectedFile(null)
    setTitle('')
    setDescription('')
    setDiarize(defaultDiarize)
    setNumSpeakers('')
    setVocabulary('')
    setValidationError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return
    const finalTitle = title.trim() || cleanTitleFromFilename(selectedFile.name)
    const speakers = Number.parseInt(numSpeakers, 10)
    await onUpload(selectedFile, finalTitle, description, {
      diarize,
      numSpeakers: diarize && speakers >= 1 && speakers <= MAX_SPEAKERS ? speakers : null,
      vocabulary: vocabulary.trim() || undefined,
    })
  }

  const isVideo = selectedFile
    ? selectedFile.type.startsWith('video/') || /\.(mp4|webm|mkv|mov|avi|wmv|m4v|flv|ts)$/i.test(selectedFile.name)
    : false

  return (
    <div className="card p-6 bg-white border border-slate-200 shadow-sm rounded-2xl space-y-5">
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Drag & Drop Area */}
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={handlePickerClick}
          className={`relative rounded-2xl border-2 border-dashed p-8 transition flex flex-col items-center justify-center text-center cursor-pointer ${dragActive
            ? 'border-blue-500 bg-blue-50/70 shadow-md ring-4 ring-blue-500/10'
            : selectedFile
              ? 'border-emerald-300 bg-emerald-50/30'
              : 'border-slate-300 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/30'
            }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,video/*,.mp3,.mp4,.wav,.m4a,.webm,.ogg,.flac,.aac,.opus,.mkv,.mov,.wmv,.avi"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleFile(file)
            }}
            className="hidden"
          />

          {!selectedFile ? (
            <div className="space-y-3.5">
              <div className="flex h-14 w-14 mx-auto items-center justify-center rounded-2xl bg-blue-50 text-[#002777] shadow-inner ring-1 ring-blue-100 group-hover:scale-105 transition-transform">
                <Upload className="h-7 w-7" />
              </div>
              <div>
                <p className="text-base font-bold text-slate-800">
                  Haz clic para explorar o arrastra tu grabación aquí
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Audio o video (MP3, WAV, M4A, MP4, WebM, FLAC, OGG, OPUS, AAC, MKV, WMV, AVI)
                </p>
                <p className="text-[11px] text-blue-700/80 mt-1.5 font-medium">
                  {showServerOptions
                    ? 'El archivo se sube al servidor y se transcribe con el proveedor configurado'
                    : 'Decodificación y transcripción 100% privada en el navegador'}
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
                  <p className="text-sm font-bold text-slate-900 truncate">{selectedFile.name}</p>
                  <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-2">
                    <span>{formatFileSize(selectedFile.size)}</span>
                    <span>•</span>
                    <span className="text-emerald-700 font-semibold flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {showServerOptions ? 'Listo para subir' : 'Listo para procesar en el navegador'}
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

        {validationError && (
          <div className="flex items-center gap-2.5 p-3 rounded-xl bg-red-50 text-red-700 text-xs border border-red-200 animate-fade-in">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{validationError}</span>
          </div>
        )}

        {selectedFile && (
          <div className="space-y-4 pt-1 animate-fade-in">
            <div>
              <label htmlFor="upload-title" className="block text-xs font-bold text-slate-700 mb-1.5">
                Título de la Reunión <span className="text-red-500">*</span>
              </label>
              <input
                id="upload-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ej. Kickoff Proyecto Pagos QR - Sprint 1"
                required
                className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777] transition"
              />
            </div>

            <div>
              <label htmlFor="upload-description" className="block text-xs font-bold text-slate-700 mb-1.5">
                Descripción o Contexto Adicional <span className="text-slate-400 font-normal">(Opcional)</span>
              </label>
              <textarea
                id="upload-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Notas de contexto, stakeholders clave o especificaciones preliminares..."
                rows={2}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777] transition"
              />
            </div>

            <fieldset className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3.5">
                <legend className="px-1 text-xs font-bold text-slate-700 flex items-center gap-1.5">
                  <Sliders className="h-3.5 w-3.5 text-[#002777]" />
                  Opciones de procesamiento
                </legend>

                <div className="flex flex-wrap items-center gap-4">
                  <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={diarize}
                      onChange={(e) => setDiarize(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-[#002777] focus:ring-[#002777]/30"
                    />
                    Identificar interlocutores
                  </label>
                  {diarize && (
                    <label className="flex items-center gap-2 text-xs text-slate-700">
                      Número de interlocutores
                      <input
                        type="number"
                        min={1}
                        max={MAX_SPEAKERS}
                        value={numSpeakers}
                        onChange={(e) => setNumSpeakers(e.target.value)}
                        placeholder="Auto"
                        className="w-20 px-2 py-1 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
                      />
                    </label>
                  )}
                </div>
                {diarize && (
                  <p className="text-[11px] text-slate-500">
                    {showServerOptions
                      ? 'La identificación automática requiere una clave de OpenAI. Sin ella, la transcripción se guarda con un único interlocutor y puedes asignarlos después.'
                      : 'Se hace en tu navegador, sin enviar el audio: la primera vez descarga unos 30 MB de modelos y alarga el proceso. Revisa y corrige los interlocutores al terminar.'}
                  </p>
                )}

                {showServerOptions && (
                  <div>
                    <label htmlFor="upload-vocabulary" className="block text-xs font-semibold text-slate-700 mb-1">
                      Vocabulario específico <span className="text-slate-400 font-normal">(opcional)</span>
                    </label>
                    <textarea
                      id="upload-vocabulary"
                      value={vocabulary}
                      onChange={(e) => setVocabulary(e.target.value)}
                      maxLength={1000}
                      rows={2}
                      placeholder="Nombres, siglas o términos que aparecen en la reunión: SAP, Historia Clínica Electrónica…"
                      className="w-full px-3 py-1.5 text-xs bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#002777]/20"
                    />
                  </div>
                )}
              </fieldset>

            {configuredModelLabel && (
              <div className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-blue-50/70 border border-blue-100 text-xs text-slate-600">
                <span className="flex items-center gap-1.5 text-slate-700">
                  <Sparkles className="h-3.5 w-3.5 text-[#002777]" />
                  <span>Motor configurado en Ajustes:</span>
                </span>
                <span className="font-bold text-[#002777]">{configuredModelLabel}</span>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={handleClear}
                disabled={isUploading}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
              >
                Cancelar
              </button>

              <button
                type="submit"
                disabled={isUploading || !title.trim()}
                className="btn-primary px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 text-xs shadow-md shadow-blue-900/10 cursor-pointer disabled:opacity-50"
              >
                <Sparkles className={`h-4 w-4 ${isUploading ? 'animate-spin' : ''}`} />
                <span>{isUploading ? 'Iniciando Transcripción...' : 'Iniciar Transcripción & Análisis'}</span>
              </button>
            </div>
          </div>
        )}
      </form>
    </div>
  )
}
