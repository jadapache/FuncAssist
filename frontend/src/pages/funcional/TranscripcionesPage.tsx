import { useState, useMemo, useEffect } from 'react'
import {
  Sparkles,
  FileText,
  Search,
  RefreshCw,
  AlertTriangle,
  ArrowRight,
  LayoutGrid,
  List,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useTranscription } from '../../hooks/useTranscription'
import type { TranscriptionResult } from '../../api/modules/transcription'
import { ConfirmationModal } from '../../components/common'
import {
  UploadArea,
  RecentTranscriptionItem,
  GenerateModal,
  FloatingTranscriptionToast,
  TranscriptionStudio,
} from '../../components/transcription'

const ITEMS_PER_PAGE = 10

export const TranscripcionesPage = () => {
  const {
    viewMode,
    openStudio,
    closeStudio,
    activeJobs,
    recentTranscriptions,
    availableModels,
    isLoadingList,
    isUploading,
    showGenerateModal,
    selectedTranscriptionId,
    activeMeetingTitle,
    currentProgress,
    handleUploadAndStart,
    handleCancelTranscription,
    handleDeleteTranscription,
    handleDismissJob,
    setShowGenerateModal,
    refreshTranscriptions,
  } = useTranscription()

  const [searchQuery, setSearchQuery] = useState('')
  const [viewStyle, setViewStyle] = useState<'grid' | 'list'>('grid')
  const [currentPage, setCurrentPage] = useState(1)

  // Delete confirmation modal state
  const [transcriptionToDelete, setTranscriptionToDelete] = useState<TranscriptionResult | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const isModelConfigured =
    !availableModels ||
    availableModels.local_available ||
    availableModels.groq_configured ||
    availableModels.openai_configured

  const filteredRecents = useMemo(() => {
    return recentTranscriptions.filter((t) => {
      if (!searchQuery.trim()) return true
      const q = searchQuery.toLowerCase()
      const titleMatch = t.metadata.title.toLowerCase().includes(q)
      const descMatch = t.metadata.description?.toLowerCase().includes(q)
      const participantsMatch = t.summary?.participants?.some((p) => p.toLowerCase().includes(q))
      return titleMatch || descMatch || participantsMatch
    })
  }, [recentTranscriptions, searchQuery])

  // Reset to page 1 on search
  useEffect(() => {
    setCurrentPage(1)
  }, [searchQuery])

  // Pagination calculation
  const totalPages = Math.max(1, Math.ceil(filteredRecents.length / ITEMS_PER_PAGE))
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE
    return filteredRecents.slice(start, start + ITEMS_PER_PAGE)
  }, [filteredRecents, currentPage])

  const confirmDelete = async () => {
    if (!transcriptionToDelete) return
    try {
      setIsDeleting(true)
      await handleDeleteTranscription(transcriptionToDelete.id)
      setTranscriptionToDelete(null)
    } finally {
      setIsDeleting(false)
    }
  }

  // If in Studio mode and a transcription is selected, render the TranscriptionStudio workspace
  if (viewMode === 'studio' && selectedTranscriptionId) {
    return (
      <div className="animate-fade-in font-sans">
        <TranscriptionStudio
          transcriptionId={selectedTranscriptionId}
          activeProgress={currentProgress}
          onBackToDashboard={closeStudio}
          onRefreshData={refreshTranscriptions}
        />
        {/* Floating toast widget in top right */}
        <FloatingTranscriptionToast
          activeJobs={activeJobs}
          onOpenStudio={(id) => openStudio(id)}
          onCancelJob={(id) => handleCancelTranscription(id)}
          onDismissJob={(id) => handleDismissJob(id)}
        />
      </div>
    )
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto font-sans pb-12 animate-fade-in">
      {/* Page Header */}
      <header>
        <div className="flex items-center gap-2">
          <p className="text-xs font-bold uppercase tracking-widest text-[#002777]">
            MÓDULO FUNCIONAL
          </p>
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-bold text-[#002777]">
            <Sparkles className="h-3 w-3" />
            IA + Whisper
          </span>
        </div>
        <h1 className="page-title mt-1">Transcripción y Análisis de Reuniones</h1>
        <p className="page-subtitle">
          Carga grabaciones de reuniones para transcribir con Whisper, identificar interlocutores, extraer minutas y generar entregables funcionales.
        </p>
      </header>

      {/* API Key Missing Warning Banner (If no model provider is configured) */}
      {!isModelConfigured && (
        <div className="card p-4 bg-amber-50 border border-amber-200 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs animate-fade-in">
          <div className="flex items-start sm:items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-800">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-amber-950 uppercase tracking-wide">
                Configuración de Motor de Transcripción Requerida
              </h3>
              <p className="text-xs text-amber-900 mt-0.5">
                No se detectó API Key para Groq ni OpenAI Whisper. Configura tu clave en Ajustes para habilitar el procesamiento en la nube.
              </p>
            </div>
          </div>

          <Link
            to="/configuracion"
            className="px-3.5 py-1.5 bg-amber-800 hover:bg-amber-900 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shrink-0 shadow-xs"
          >
            <span>Configurar Ajustes</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      {/* Upload Area */}
      <div className="w-full">
        <UploadArea
          onUpload={async (file, title, desc) => {
            await handleUploadAndStart(file, title, desc)
          }}
          isUploading={isUploading}
          configuredModelLabel={availableModels?.active_model_label}
        />
      </div>

      {/* Transcriptions Section */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Transcripciones
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Consulta tus grabaciones procesadas, visualiza sus minutas y genera entregables.
            </p>
          </div>

          <div className="flex items-center gap-2.5 self-start sm:self-auto w-full sm:w-auto">
            {recentTranscriptions.length > 0 && (
              <div className="relative flex-1 sm:w-60">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Buscar por título..."
                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#002777]/20 focus:border-[#002777] shadow-2xs"
                />
              </div>
            )}

            {/* View Switcher: Grid vs List */}
            <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 shrink-0">
              <button
                type="button"
                onClick={() => setViewStyle('grid')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${
                  viewStyle === 'grid'
                    ? 'bg-white text-[#002777] shadow-xs'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
                title="Vista en Cuadrícula"
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setViewStyle('list')}
                className={`p-1.5 rounded-lg transition cursor-pointer ${
                  viewStyle === 'list'
                    ? 'bg-white text-[#002777] shadow-xs'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
                title="Vista en Lista"
              >
                <List className="h-4 w-4" />
              </button>
            </div>

            {/* Refresh Button */}
            <button
              type="button"
              onClick={refreshTranscriptions}
              disabled={isLoadingList}
              className="p-2 text-slate-500 hover:text-[#002777] hover:bg-slate-100 bg-white border border-slate-200 rounded-xl transition cursor-pointer shadow-2xs shrink-0"
              title="Actualizar transcripciones"
            >
              <RefreshCw className={`h-4 w-4 ${isLoadingList ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {recentTranscriptions.length === 0 && activeJobs.length === 0 ? (
          <div className="card p-12 bg-white border border-slate-200 rounded-2xl text-center space-y-3 shadow-xs">
            <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-2xl bg-blue-50 text-[#002777]">
              <FileText className="h-6 w-6" />
            </div>
            <h3 className="text-sm font-bold text-slate-900">
              Aún no tienes transcripciones registradas
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Sube una grabación de audio o video en el área superior para comenzar a generar minutas y documentación funcional.
            </p>
          </div>
        ) : filteredRecents.length === 0 ? (
          <div className="card p-8 bg-white border border-slate-200 rounded-2xl text-center text-xs text-slate-500">
            No se encontraron transcripciones que coincidan con "{searchQuery}".
          </div>
        ) : (
          <div className="space-y-4">
            {/* Grid or List Display */}
            {viewStyle === 'grid' ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {paginatedItems.map((item) => (
                  <RecentTranscriptionItem
                    key={item.id}
                    transcription={item}
                    viewMode="grid"
                    onOpenSummary={(id) => openStudio(id)}
                    onRequestDelete={(t) => setTranscriptionToDelete(t)}
                  />
                ))}
              </div>
            ) : (
              <div className="space-y-2.5">
                {paginatedItems.map((item) => (
                  <RecentTranscriptionItem
                    key={item.id}
                    transcription={item}
                    viewMode="list"
                    onOpenSummary={(id) => openStudio(id)}
                    onRequestDelete={(t) => setTranscriptionToDelete(t)}
                  />
                ))}
              </div>
            )}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-100 text-xs text-slate-600">
                <p>
                  Mostrando{' '}
                  <span className="font-bold text-slate-900">
                    {(currentPage - 1) * ITEMS_PER_PAGE + 1}
                  </span>{' '}
                  a{' '}
                  <span className="font-bold text-slate-900">
                    {Math.min(currentPage * ITEMS_PER_PAGE, filteredRecents.length)}
                  </span>{' '}
                  de{' '}
                  <span className="font-bold text-slate-900">{filteredRecents.length}</span>{' '}
                  transcripciones
                </p>

                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer text-slate-700"
                    title="Página anterior"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>

                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
                    <button
                      key={pageNum}
                      type="button"
                      onClick={() => setCurrentPage(pageNum)}
                      className={`min-w-[32px] h-8 px-2 rounded-lg font-bold text-xs transition cursor-pointer ${
                        currentPage === pageNum
                          ? 'bg-[#002777] text-white'
                          : 'bg-white hover:bg-slate-100 text-slate-700 border border-slate-200'
                      }`}
                    >
                      {pageNum}
                    </button>
                  ))}

                  <button
                    type="button"
                    disabled={currentPage === totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer text-slate-700"
                    title="Página siguiente"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Floating Background Task Toast (Top-Right Widget) */}
      <FloatingTranscriptionToast
        activeJobs={activeJobs}
        onOpenStudio={(id) => openStudio(id)}
        onCancelJob={(id) => handleCancelTranscription(id)}
        onDismissJob={(id) => handleDismissJob(id)}
      />

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={Boolean(transcriptionToDelete)}
        title="¿Eliminar Transcripción?"
        message={`¿Estás seguro de que deseas eliminar permanentemente "${
          transcriptionToDelete?.metadata.title || 'esta transcripción'
        }" y sus archivos asociados? Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar Transcripción"
        cancelLabel="Cancelar"
        isDestructive={true}
        isLoading={isDeleting}
        onConfirm={confirmDelete}
        onClose={() => setTranscriptionToDelete(null)}
      />

      {/* Generate Deliverables Modal */}
      <GenerateModal
        isOpen={showGenerateModal}
        transcriptionId={selectedTranscriptionId}
        meetingTitle={activeMeetingTitle}
        onClose={() => setShowGenerateModal(false)}
      />
    </div>
  )
}

export default TranscripcionesPage
