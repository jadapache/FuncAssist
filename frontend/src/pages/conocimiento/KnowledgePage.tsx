import type { FormEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  FileCode,
  Grid,
  HardDrive,
  Layers,
  List,
  Plus,
  RefreshCw,
  Search,
  Tag,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react'
import { api, type KnowledgeDocument } from '../../api/client'
import { ConfirmationModal, PageHeader } from '../../components/common'
import { useToast } from '../../context/ToastContext'

const ACCEPTED_TYPES = '.pdf,.docx,.doc,.md,.txt,.json,.html,.htm'
const PRESET_TAGS = ['prd', 'especificación', 'arquitectura', 'qa', 'reglas', 'reunión']

function getFileExtension(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.pop()!.toUpperCase() : 'DOC'
}

function getFileExtensionStyle(filename: string): { bg: string; text: string; ring: string } {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  if (ext === 'pdf') return { bg: 'bg-rose-50', text: 'text-rose-700', ring: 'ring-rose-200' }
  if (ext === 'docx' || ext === 'doc') return { bg: 'bg-blue-50', text: 'text-blue-700', ring: 'ring-blue-200' }
  if (ext === 'md') return { bg: 'bg-purple-50', text: 'text-purple-700', ring: 'ring-purple-200' }
  if (ext === 'json') return { bg: 'bg-amber-50', text: 'text-amber-700', ring: 'ring-amber-200' }
  if (ext === 'html' || ext === 'htm') return { bg: 'bg-emerald-50', text: 'text-emerald-700', ring: 'ring-emerald-200' }
  return { bg: 'bg-slate-50', text: 'text-[#002777]', ring: 'ring-slate-200' }
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

function formatFileSize(bytes: number): string {
  if (!bytes || isNaN(bytes)) return '0 KB'
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.round(bytes / 1024)} KB`
}

export const KnowledgePage = () => {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Data State
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [busy, setBusy] = useState(false)

  // Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedTags, setSelectedTags] = useState<string[]>(['prd'])
  const [customTagInput, setCustomTagInput] = useState('')

  // Filter & Pagination State
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTagFilter, setSelectedTagFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = viewMode === 'grid' ? 6 : 8

  // Modal State
  const [docToDelete, setDocToDelete] = useState<KnowledgeDocument | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // RAG Tester State
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState({ knowledge: true, jira: false, github: false })
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [testingRAG, setTestingRAG] = useState(false)

  const load = useCallback(async () => {
    setLoadingDocs(true)
    try {
      const data = await api.listDocuments()
      setDocuments(data.documents || [])
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al cargar los documentos'
      toast.error(msg)
    } finally {
      setLoadingDocs(false)
    }
  }, [toast])

  useEffect(() => {
    void load()
  }, [load])

  // Drag & Drop Handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      setSelectedFile(files[0])
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0])
    }
  }

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }

  const handleAddCustomTag = () => {
    const clean = customTagInput.trim().toLowerCase().replace(/[^a-záéíóúñ0-9_\-]/g, '')
    if (clean && !selectedTags.includes(clean)) {
      setSelectedTags((prev) => [...prev, clean])
      setCustomTagInput('')
    }
  }

  const removeSelectedTag = (tagToRemove: string) => {
    setSelectedTags((prev) => prev.filter((t) => t !== tagToRemove))
  }

  // Upload Submission
  const handleUpload = async (e?: FormEvent) => {
    if (e) e.preventDefault()
    if (!selectedFile) {
      toast.warning('Selecciona o arrastra un archivo primero.')
      return
    }

    setBusy(true)
    try {
      const allTags = selectedTags.join(',')
      const uploaded = await api.uploadDocument(selectedFile, allTags)

      // Clean up state safely
      setSelectedFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      await load()
      toast.success(
        `"${uploaded.document.filename}" procesado e indexado con ${uploaded.document.chunk_count} fragmentos en SQLite FTS5.`,
      )
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la carga del documento'
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const confirmDeleteDoc = async () => {
    if (!docToDelete) return
    setIsDeleting(true)
    setBusy(true)
    try {
      await api.deleteDocument(docToDelete.id)
      await load()
      toast.success(`Se eliminó "${docToDelete.filename}".`)
      setDocToDelete(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la eliminación'
      toast.error(msg)
    } finally {
      setBusy(false)
      setIsDeleting(false)
    }
  }

  // Retrieve / Test RAG
  const handleRetrieve = async (e: FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setTestingRAG(true)
    try {
      const active = Object.entries(sources)
        .filter(([, on]) => on)
        .map(([key]) => key)
      const data = await api.retrieve(query, active)
      setResult(data)
      toast.success('Búsqueda RAG completada.')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la recuperación de información'
      toast.error(msg)
    } finally {
      setTestingRAG(false)
    }
  }

  // Tags extracted across all documents
  const allAvailableDocTags = useMemo(() => {
    const tagsSet = new Set<string>()
    documents.forEach((doc) => {
      ; (doc.tags || []).forEach((t) => tagsSet.add(t.toLowerCase()))
    })
    return Array.from(tagsSet)
  }, [documents])

  // Filtered & Paginated Documents
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const queryLower = searchQuery.toLowerCase().trim()
      const matchesSearch =
        !queryLower ||
        doc.filename.toLowerCase().includes(queryLower) ||
        (doc.tags || []).some((t) => t.toLowerCase().includes(queryLower))

      const matchesTag =
        selectedTagFilter === 'all' ||
        (doc.tags || []).map((t) => t.toLowerCase()).includes(selectedTagFilter.toLowerCase())

      return matchesSearch && matchesTag
    })
  }, [documents, searchQuery, selectedTagFilter])

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / itemsPerPage))

  const paginatedDocuments = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage
    return filteredDocuments.slice(start, start + itemsPerPage)
  }, [filteredDocuments, currentPage, itemsPerPage])

  // Reset page if search filter changes
  useEffect(() => {
    setCurrentPage(1)
  }, [searchQuery, selectedTagFilter, viewMode])

  return (
    <div className="space-y-8 pb-12 font-sans">
      <PageHeader
        eyebrow="SISTEMA RAG & INDEXACIÓN"
        title="Biblioteca de Conocimiento"
        subtitle="Indexa PRDs, especificaciones y actas de reunión. Almacenados en SQLite FTS5 con búsqueda BM25 nativa y soporte para diacríticos en español."
        actions={
          <Link
            to="/settings?tab=knowledge"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold text-[#002777] bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50/50 rounded-xl transition shadow-2xs cursor-pointer group"
          >
            <Database className="h-4 w-4 text-[#002777] group-hover:scale-110 transition-transform" />
            <span>Configurar Motor SQLite & Red</span>
          </Link>
        }
      />

      {/* 2. Drag & Drop File Upload Section */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 text-[#002777]">
              <UploadCloud className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Cargar e Indexar Documentos</h2>
              <p className="text-xs text-slate-500">
                Formatos soportados: PDF, Word (.docx), Markdown (.md), TXT, HTML, JSON.
              </p>
            </div>
          </div>
        </div>

        {/* Drop Zone Box */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`relative border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer ${isDragging
              ? 'border-blue-500 bg-blue-50/60 scale-[0.99]'
              : selectedFile
                ? 'border-emerald-400 bg-emerald-50/30'
                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50/80 bg-slate-50/40'
            }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileChange}
            className="hidden"
            aria-label="Seleccionar archivo"
          />

          {!selectedFile ? (
            <div className="flex flex-col items-center justify-center gap-3">
              <div className="h-12 w-12 rounded-2xl bg-blue-100/80 text-[#002777] flex items-center justify-center shadow-2xs">
                <UploadCloud className="h-6 w-6" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-bold text-slate-800">
                  Arrastra tu archivo aquí o{' '}
                  <span className="text-[#002777] underline decoration-blue-300 underline-offset-2">
                    haz clic para explorar
                  </span>
                </p>
                <p className="text-xs text-slate-400">
                  Máximo 50 MB por archivo. Se dividirá automáticamente en fragmentos semánticos.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-1.5 pt-2">
                {['.PDF', '.DOCX', '.MD', '.TXT', '.JSON', '.HTML'].map((ext) => (
                  <span
                    key={ext}
                    className="px-2 py-0.5 text-[10px] font-mono font-bold bg-white text-slate-600 border border-slate-200 rounded-md shadow-2xs"
                  >
                    {ext}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            /* Selected File Preview */
            <div
              className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 bg-white rounded-xl border border-emerald-200 shadow-xs"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <div
                  className={`h-11 w-11 shrink-0 rounded-xl flex items-center justify-center font-mono font-extrabold text-xs shadow-2xs ${getFileExtensionStyle(selectedFile.name).bg
                    } ${getFileExtensionStyle(selectedFile.name).text} ${getFileExtensionStyle(selectedFile.name).ring
                    } ring-1`}
                >
                  {getFileExtension(selectedFile.name)}
                </div>
                <div className="text-left min-w-0">
                  <p className="text-sm font-bold text-slate-900 truncate" title={selectedFile.name}>
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-slate-500 font-medium">
                    {formatFileSize(selectedFile.size)} · Listo para procesar
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedFile(null)
                    if (fileInputRef.current) fileInputRef.current.value = ''
                  }}
                  className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer"
                  title="Cambiar archivo"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Tags & Processing Controls */}
        <div className="space-y-3 pt-1">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
              <Tag className="h-3.5 w-3.5 text-[#002777]" />
              <span>Etiquetas del Documento (para filtrado RAG)</span>
            </label>
            <span className="text-[11px] text-slate-400 font-medium">
              {selectedTags.length} seleccionada(s)
            </span>
          </div>

          {/* Preset Tags + Active Tags */}
          <div className="flex flex-wrap items-center gap-2">
            {PRESET_TAGS.map((tag) => {
              const active = selectedTags.includes(tag)
              return (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggleTag(tag)}
                  className={`px-3 py-1 rounded-full text-xs font-semibold transition-all cursor-pointer border ${active
                      ? 'bg-[#002777] text-white border-[#002777] shadow-2xs'
                      : 'bg-slate-100 hover:bg-slate-200/80 text-slate-700 border-slate-200'
                    }`}
                >
                  {active ? `✓ ${tag}` : `+ ${tag}`}
                </button>
              )
            })}

            {/* Custom Added Tags */}
            {selectedTags
              .filter((t) => !PRESET_TAGS.includes(t))
              .map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200 shadow-2xs"
                >
                  <span>#{tag}</span>
                  <button
                    type="button"
                    onClick={() => removeSelectedTag(tag)}
                    className="hover:text-red-600 cursor-pointer"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}

            {/* Input to add custom tag */}
            <div className="inline-flex items-center gap-1">
              <input
                type="text"
                value={customTagInput}
                onChange={(e) => setCustomTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleAddCustomTag()
                  }
                }}
                placeholder="Otra etiqueta..."
                className="px-2.5 py-1 text-xs border border-slate-300 rounded-lg bg-white text-slate-800 placeholder-slate-400 focus:outline-hidden focus:ring-1 focus:ring-[#002777] w-28"
              />
              <button
                type="button"
                onClick={handleAddCustomTag}
                disabled={!customTagInput.trim()}
                className="p-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 disabled:opacity-40 cursor-pointer"
                title="Agregar etiqueta"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Submit Action Button */}
        <div className="flex justify-end pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={() => void handleUpload()}
            disabled={busy || !selectedFile}
            className="px-6 py-2.5 bg-[#002777] hover:bg-[#001f5f] text-white text-xs font-bold rounded-xl transition shadow-xs disabled:opacity-40 flex items-center gap-2 cursor-pointer"
          >
            {busy ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span>Extrayendo e indexando en FTS5...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4" />
                <span>Cargar e Indexar en Base de Conocimiento</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 3. Stored Documents Section (Cards Layout with Search & Pagination) */}
      <section className="space-y-4">
        {/* Controls Toolbar: Title, Search Bar, Tag Filter, View Switcher, Refresh */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-900">Documentos Almacenados</h2>
            <span className="px-2.5 py-0.5 text-xs font-extrabold bg-blue-50 text-[#002777] rounded-full border border-blue-200">
              {filteredDocuments.length}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Search Input */}
            <div className="relative flex-1 sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar por nombre o etiqueta..."
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl text-slate-800 placeholder-slate-400 focus:bg-white focus:ring-2 focus:ring-[#002777] focus:outline-hidden transition"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Tag Filter Dropdown */}
            {allAvailableDocTags.length > 0 && (
              <div className="relative">
                <select
                  value={selectedTagFilter}
                  onChange={(e) => setSelectedTagFilter(e.target.value)}
                  className="pl-3 pr-8 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl text-slate-700 font-medium focus:bg-white focus:ring-2 focus:ring-[#002777] outline-hidden cursor-pointer"
                >
                  <option value="all">Todas las etiquetas</option>
                  {allAvailableDocTags.map((tag) => (
                    <option key={tag} value={tag}>
                      #{tag}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* View Mode Toggle */}
            <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
              <button
                type="button"
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${viewMode === 'grid'
                    ? 'bg-white text-[#002777] shadow-2xs font-bold'
                    : 'text-slate-500 hover:text-slate-800'
                  }`}
                title="Vista en tarjetas"
              >
                <Grid className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${viewMode === 'list'
                    ? 'bg-white text-[#002777] shadow-2xs font-bold'
                    : 'text-slate-500 hover:text-slate-800'
                  }`}
                title="Vista en lista"
              >
                <List className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Refresh Button */}
            <button
              type="button"
              onClick={() => void load()}
              disabled={loadingDocs || busy}
              className="p-2 text-slate-500 hover:text-[#002777] hover:bg-slate-100 rounded-xl border border-slate-200 transition cursor-pointer disabled:opacity-40"
              title="Actualizar lista"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingDocs ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Documents Grid / List */}
        {loadingDocs ? (
          <div className="p-12 text-center text-slate-500 bg-white rounded-2xl border border-slate-200 space-y-3">
            <RefreshCw className="h-8 w-8 animate-spin text-[#002777] mx-auto opacity-70" />
            <p className="text-xs font-semibold text-slate-700">Cargando catálogo documental...</p>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="p-12 text-center text-slate-500 bg-white rounded-2xl border border-slate-200 space-y-3">
            <div className="h-12 w-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
              <FileCode className="h-6 w-6" />
            </div>
            <div className="space-y-1 max-w-sm mx-auto">
              <p className="text-sm font-bold text-slate-800">
                {documents.length === 0
                  ? 'No hay documentos almacenados'
                  : 'Ningún documento coincide con los filtros'}
              </p>
              <p className="text-xs text-slate-400 leading-relaxed">
                {documents.length === 0
                  ? 'Sube un archivo en el recuadro superior para que esté disponible en las consultas RAG.'
                  : 'Prueba cambiando el término de búsqueda o seleccionando otra etiqueta.'}
              </p>
            </div>
          </div>
        ) : viewMode === 'grid' ? (
          /* GRID VIEW (Matching RecentTranscriptionItem Cards) */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {paginatedDocuments.map((doc) => {
              const extStyle = getFileExtensionStyle(doc.filename)
              const ext = getFileExtension(doc.filename)

              return (
                <div
                  key={doc.id}
                  className="group relative p-5 bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50/15 rounded-2xl shadow-xs transition-all duration-200 hover:shadow-md flex flex-col justify-between space-y-4"
                >
                  <div className="space-y-3">
                    {/* Header with Icon, Title, and Delete Button on top-right */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0 flex-1">
                        <div
                          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl font-mono font-bold text-xs shadow-2xs group-hover:scale-105 transition ring-1 ${extStyle.bg} ${extStyle.text} ${extStyle.ring}`}
                        >
                          {ext}
                        </div>
                        <div className="min-w-0 flex-1 space-y-1 pr-1">
                          <h4
                            className="text-sm font-bold text-slate-900 group-hover:text-[#002777] transition truncate"
                            title={doc.filename}
                          >
                            {doc.filename}
                          </h4>
                          {/* Tags Pills */}
                          <div className="flex flex-wrap gap-1">
                            {(doc.tags || []).length > 0 ? (
                              doc.tags.map((t, tIdx) => (
                                <span
                                  key={tIdx}
                                  className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200/80"
                                >
                                  #{t}
                                </span>
                              ))
                            ) : (
                              <span className="text-[10px] text-slate-400 italic">sin etiquetas</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Delete Button on Top Right */}
                      <button
                        type="button"
                        onClick={() => setDocToDelete(doc)}
                        className="p-1.5 -mr-1 -mt-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition cursor-pointer shrink-0"
                        title="Eliminar documento"
                        aria-label={`Eliminar ${doc.filename}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                    {/* Metadata Row: Fecha • Fragmentos • Caracteres */}
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400 pt-3 border-t border-slate-100">
                      <span className="flex items-center gap-1 font-medium text-slate-600">
                        <Calendar className="h-3 w-3 text-slate-400 shrink-0" />
                        <span>{formatDateTime(doc.uploaded_at)}</span>
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1 font-medium text-slate-600">
                        <Layers className="h-3 w-3 text-slate-400 shrink-0" />
                        <span>{doc.chunk_count} frags</span>
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1 font-medium text-slate-600">
                        <HardDrive className="h-3 w-3 text-slate-400 shrink-0" />
                        <span>{doc.char_count?.toLocaleString() || 0} chars</span>
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          /* LIST VIEW */
          <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-100 shadow-xs overflow-hidden">
            {paginatedDocuments.map((doc) => {
              const extStyle = getFileExtensionStyle(doc.filename)
              const ext = getFileExtension(doc.filename)

              return (
                <div
                  key={doc.id}
                  className="p-4 hover:bg-slate-50/80 transition flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="flex items-start sm:items-center gap-3.5 min-w-0 flex-1">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-mono font-bold text-xs ring-1 ${extStyle.bg} ${extStyle.text} ${extStyle.ring}`}
                    >
                      {ext}
                    </div>

                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-slate-900 truncate" title={doc.filename}>
                          {doc.filename}
                        </h4>
                        <div className="flex flex-wrap gap-1">
                          {(doc.tags || []).map((t, tIdx) => (
                            <span
                              key={tIdx}
                              className="px-1.5 py-0.5 text-[10px] font-semibold bg-slate-100 text-slate-600 rounded border border-slate-200"
                            >
                              #{t}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2.5 text-[11px] text-slate-400">
                        <span className="flex items-center gap-1 font-medium text-slate-600">
                          <Calendar className="h-3 w-3 text-slate-400 shrink-0" />
                          <span>{formatDateTime(doc.uploaded_at)}</span>
                        </span>
                        <span>•</span>
                        <span className="flex items-center gap-1 font-medium text-slate-600">
                          <Layers className="h-3 w-3 text-slate-400 shrink-0" />
                          <span>{doc.chunk_count} fragmentos FTS5</span>
                        </span>
                        <span>•</span>
                        <span className="flex items-center gap-1 font-medium text-slate-600">
                          <HardDrive className="h-3 w-3 text-slate-400 shrink-0" />
                          <span>{doc.char_count?.toLocaleString() || 0} caracteres</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                    <button
                      type="button"
                      onClick={() => setDocToDelete(doc)}
                      className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition cursor-pointer"
                      title="Eliminar documento"
                      aria-label={`Eliminar ${doc.filename}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Pagination Bar */}
        {filteredDocuments.length > itemsPerPage && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white px-5 py-3.5 rounded-2xl border border-slate-200 shadow-2xs">
            <span className="text-xs text-slate-500 font-medium">
              Mostrando{' '}
              <strong className="text-slate-800">
                {(currentPage - 1) * itemsPerPage + 1}
              </strong>{' '}
              a{' '}
              <strong className="text-slate-800">
                {Math.min(currentPage * itemsPerPage, filteredDocuments.length)}
              </strong>{' '}
              de <strong className="text-slate-800">{filteredDocuments.length}</strong> documentos
            </span>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 disabled:opacity-40 transition cursor-pointer"
                title="Página anterior"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>

              {Array.from({ length: totalPages }).map((_, idx) => {
                const pageNum = idx + 1
                return (
                  <button
                    key={pageNum}
                    type="button"
                    onClick={() => setCurrentPage(pageNum)}
                    className={`h-7 w-7 rounded-lg text-xs font-bold transition cursor-pointer ${currentPage === pageNum
                        ? 'bg-[#002777] text-white shadow-2xs'
                        : 'text-slate-600 hover:bg-slate-100'
                      }`}
                  >
                    {pageNum}
                  </button>
                )
              })}

              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 disabled:opacity-40 transition cursor-pointer"
                title="Página siguiente"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </section>

      {/* 4. RAG Retrieval Tester (Interactive Test Bench) */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-purple-50 text-purple-700">
              <Search className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Verificador de Recuperación RAG (FTS5 + BM25)
              </h2>
              <p className="text-xs text-slate-500">
                Prueba qué fragmentos son recuperados y clasificados por relevancia ante una consulta.
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={(e) => void handleRetrieve(e)} className="space-y-4">
          <div className="flex flex-wrap items-center gap-4 text-xs font-semibold text-slate-700">
            <span className="text-slate-400 uppercase tracking-wider text-[10px]">Fuentes:</span>
            {(['knowledge', 'jira', 'github'] as const).map((key) => (
              <label key={key} className="inline-flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={sources[key]}
                  onChange={(e) => setSources((prev) => ({ ...prev, [key]: e.target.checked }))}
                  className="rounded text-[#002777] focus:ring-[#002777]"
                />
                <span>{key === 'knowledge' ? 'Biblioteca SQLite FTS5' : key.toUpperCase()}</span>
              </label>
            ))}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Escribe una consulta de prueba (ej: ¿Cuáles son las reglas de autenticación?)..."
              className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:bg-white focus:ring-2 focus:ring-[#002777] outline-hidden transition"
              required
            />
            <button
              type="submit"
              disabled={testingRAG || !query.trim()}
              className="px-5 py-2.5 bg-[#002777] hover:bg-[#001f5f] text-white text-xs font-bold rounded-xl transition shadow-xs disabled:opacity-40 flex items-center gap-2 cursor-pointer"
            >
              {testingRAG ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              <span>{testingRAG ? 'Buscando...' : 'Buscar Fragmentos'}</span>
            </button>
          </div>
        </form>

        {/* Retrieval Results */}
        {result && (
          <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
            <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
              <span>
                Fuentes utilizadas:{' '}
                <strong className="text-slate-800">
                  {((result.used_sources as string[]) || []).join(', ') || 'ninguna'}
                </strong>
              </span>
              <span>
                Fragmentos obtenidos:{' '}
                <strong className="text-[#002777]">
                  {((result.chunks as Array<Record<string, unknown>>) || []).length}
                </strong>
              </span>
            </div>

            <div className="space-y-2.5">
              {((result.chunks as Array<Record<string, unknown>>) || []).map((chunk, idx) => (
                <div
                  key={String(chunk.id || idx)}
                  className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-1.5 hover:bg-slate-100/70 transition"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-slate-900 flex items-center gap-1.5">
                      <span className="h-5 w-5 rounded-full bg-blue-100 text-[#002777] flex items-center justify-center text-[10px]">
                        {idx + 1}
                      </span>
                      {String(chunk.title || 'Fragmento')}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white text-slate-600 border border-slate-200">
                      {String(chunk.source_type)} · {String(chunk.source_label)}
                    </span>
                  </div>
                  <p className="text-slate-600 whitespace-pre-wrap leading-relaxed font-sans pl-6">
                    {String(chunk.text || '').slice(0, 450)}
                    {String(chunk.text || '').length > 450 ? '...' : ''}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Modal for Document Deletion */}
      <ConfirmationModal
        isOpen={Boolean(docToDelete)}
        title="Eliminar Documento de la Biblioteca"
        message={`¿Estás seguro de que deseas eliminar "${docToDelete?.filename}" y todos sus fragmentos indexados de la base de conocimiento SQLite?`}
        confirmLabel="Eliminar Definitivamente"
        cancelLabel="Cancelar"
        variant="danger"
        isDestructive
        isLoading={isDeleting}
        onConfirm={confirmDeleteDoc}
        onClose={() => setDocToDelete(null)}
      />
    </div>
  )
}
