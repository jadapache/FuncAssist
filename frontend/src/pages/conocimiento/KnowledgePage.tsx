import type { FormEvent } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { api, type KnowledgeDocument } from '../../api/client'
import { useToast } from '../../context/ToastContext'
import { Link } from 'react-router-dom'
import { Database } from 'lucide-react'
import { ConfirmationModal } from '../../components/common'

const ACCEPTED_TYPES = '.pdf,.docx,.md,.txt,.json,.html,.htm'

export const KnowledgePage = () => {
  const { toast } = useToast()
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [tags, setTags] = useState('prd')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState({ knowledge: true, jira: false, github: false })
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [, setError] = useState<string | null>(null)
  const [, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [docToDelete, setDocToDelete] = useState<KnowledgeDocument | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoadingDocs(true)
    try {
      const data = await api.listDocuments()
      setDocuments(data.documents)
    } finally {
      setLoadingDocs(false)
    }
  }, [])

  useEffect(() => {
    void load().catch((err) => {
      const msg = err instanceof Error ? err.message : 'Error al cargar los documentos'
      setError(msg)
      toast.error(msg)
    })
  }, [load, toast])

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!selectedFile) {
      const msg = 'Selecciona un archivo primero, luego haz clic en Cargar e procesar.'
      setError(msg)
      toast.warning(msg)
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const uploaded = await api.uploadDocument(selectedFile, tags)
      setSelectedFile(null)
      event.currentTarget.reset()
      await load()
      const successMsg = `"${uploaded.document.filename}" procesado con ${uploaded.document.chunk_count} fragmentos.`
      setMessage(successMsg)
      toast.success(successMsg)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la carga'
      setError(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const confirmDeleteDoc = async () => {
    if (!docToDelete) return
    setIsDeleting(true)
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await api.deleteDocument(docToDelete.id)
      await load()
      const successMsg = `Se eliminó "${docToDelete.filename}".`
      setMessage(successMsg)
      toast.success(successMsg)
      setDocToDelete(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la eliminación'
      setError(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
      setIsDeleting(false)
    }
  }

  const handleRetrieve = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const active = Object.entries(sources)
        .filter(([, on]) => on)
        .map(([key]) => key)
      const data = await api.retrieve(query, active)
      setResult(data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la recuperación de información'
      setError(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const formatDate = (value: string) => {
    try {
      return new Date(value).toLocaleString()
    } catch {
      return value
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--color-ink-muted)]">Conocimiento</p>
          <h1 className="font-[family-name:var(--font-display)] text-5xl">Biblioteca de Documentos</h1>
          <p className="max-w-2xl text-[var(--color-ink-muted)]">
            Sube PRDs y especificaciones. Se indexan en SQLite FTS5 con soporte BM25 y diacríticos en español para búsquedas de PM y QA.
          </p>
        </div>
        <Link
          to="/settings?tab=knowledge"
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold text-[#002777] bg-blue-50 border border-blue-200 rounded-xl hover:bg-blue-100 transition shadow-2xs"
        >
          <Database className="h-4 w-4" />
          <span>Configurar Motor SQLite & Red</span>
        </Link>
      </header>



      <form onSubmit={(event) => void handleUpload(event)} className="space-y-4 rounded-xl border border-[var(--color-border)] bg-white/60 p-5">
        <h2 className="text-lg font-semibold">Cargar documento</h2>
        <p className="text-sm text-[var(--color-ink-muted)]">
          Soportados: PDF, Word, Markdown, texto, JSON, HTML. Selecciona un archivo y haz clic en Cargar e procesar.
        </p>
        <input
          name="file"
          type="file"
          accept={ACCEPTED_TYPES}
          aria-label="Cargar documento"
          className="block w-full text-sm"
          onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
        />
        {selectedFile ? (
          <p className="text-sm">
            Seleccionado: <span className="font-medium">{selectedFile.name}</span> ({Math.round(selectedFile.size / 1024)} KB)
          </p>
        ) : null}
        <label className="block text-sm">
          <span className="mb-1 block text-[var(--color-ink-muted)]">Etiquetas (separadas por comas)</span>
          <input
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            className="input-field"
            aria-label="Etiquetas del documento"
          />
        </label>
        <button type="submit" disabled={busy || !selectedFile} className="btn-primary disabled:opacity-50">
          {busy ? 'Cargando…' : 'Cargar e procesar'}
        </button>
      </form>

      <section className="space-y-4 rounded-xl border border-[var(--color-border)] bg-white/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Documentos almacenados ({documents.length})</h2>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loadingDocs || busy}
            className="btn-secondary text-sm disabled:opacity-50"
          >
            Actualizar
          </button>
        </div>

        {loadingDocs ? (
          <p className="text-sm text-[var(--color-ink-muted)]">Cargando documentos…</p>
        ) : documents.length === 0 ? (
          <p className="text-sm text-[var(--color-ink-muted)]">
            Aún no hay documentos almacenados. Sube un archivo arriba para que aparezca aquí y esté disponible para búsquedas.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {documents.map((doc) => (
              <li key={doc.id} className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{doc.filename}</p>
                  <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                    {doc.chunk_count} fragmentos · {doc.tags.join(', ') || 'sin etiqueta'} · cargado {formatDate(doc.uploaded_at)}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  className="text-sm text-[var(--color-bad)] hover:underline cursor-pointer disabled:opacity-50"
                  onClick={() => setDocToDelete(doc)}
                  aria-label={`Eliminar ${doc.filename}`}
                >
                  Eliminar
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <form onSubmit={(event) => void handleRetrieve(event)} className="space-y-4 rounded-xl border border-[var(--color-border)] bg-white/60 p-5">
        <h2 className="text-lg font-semibold">Probar recuperación de información</h2>
        <fieldset className="flex flex-wrap gap-4 text-sm">
          <legend className="sr-only">Fuentes</legend>
          {(['knowledge', 'jira', 'github'] as const).map((key) => (
            <label key={key} className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={sources[key]}
                onChange={(event) => setSources((prev) => ({ ...prev, [key]: event.target.checked }))}
              />
              {key === 'knowledge' ? 'Biblioteca' : key}
            </label>
          ))}
        </fieldset>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="¿Qué consulta deseas probar?"
          className="input-field"
          aria-label="Consulta de recuperación"
          required
        />
        <button type="submit" disabled={busy} className="btn-primary">
          Buscar fragmentos
        </button>
      </form>

      {result ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Fragmentos recuperados</h2>
          <p className="text-sm text-[var(--color-ink-muted)]">
            Utilizados: {((result.used_sources as string[]) || []).join(', ') || 'ninguno'} · Faltantes:{' '}
            {((result.missing_sources as string[]) || []).join(', ') || 'ninguno'}
          </p>
          <div className="space-y-3">
            {((result.chunks as Array<Record<string, unknown>>) || []).map((chunk, index) => (
              <article key={String(chunk.id)} className="rounded-lg border border-[var(--color-border)] bg-white/70 p-4 text-sm">
                <p className="font-medium">
                  [{index + 1}] {String(chunk.title)}
                </p>
                <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-ink-muted)]">
                  {String(chunk.source_type)} · {String(chunk.source_label)}
                </p>
                <p className="mt-2 whitespace-pre-wrap text-[var(--color-ink-muted)]">{String(chunk.text).slice(0, 500)}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <ConfirmationModal
        isOpen={Boolean(docToDelete)}
        title="Eliminar Documento de la Biblioteca"
        message={`¿Estás seguro de que deseas eliminar "${docToDelete?.filename}" de la biblioteca de conocimiento? Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar"
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
