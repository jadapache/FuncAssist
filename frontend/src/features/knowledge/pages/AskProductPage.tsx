import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { FileText, Paperclip, Send, Trash2, Upload, X } from 'lucide-react'
import { api, type GroundedResult, type KnowledgeDocument } from '../../../api/client'
import { GroundedResultView, PageHeader } from '../../../components/common'
import { useToast } from '../../../context/ToastContext'

const SOURCE_OPTIONS = [
  { id: 'jira', label: 'Jira' },
  { id: 'github', label: 'GitHub' },
  { id: 'gitlab', label: 'GitLab' },
  { id: 'knowledge', label: 'Documentos / PRDs' },
]

const ACCEPT = '.pdf,.docx,.md,.txt,.json'

export const AskProductPage = () => {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string[]>(['knowledge', 'jira', 'github'])
  const [files, setFiles] = useState<File[]>([])
  const [uploaded, setUploaded] = useState<KnowledgeDocument[]>([])
  const [result, setResult] = useState<GroundedResult | null>(null)
  const [, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(false)

  const documentIds = uploaded.map((doc) => doc.id)

  const handlePickFiles = (picked: FileList | null) => {
    if (!picked?.length) return
    setFiles((prev) => {
      const names = new Set(prev.map((file) => file.name))
      const next = [...prev]
      for (const file of Array.from(picked)) {
        if (!names.has(file.name)) next.push(file)
      }
      return next
    })
  }

  const handleUpload = async () => {
    if (!files.length) {
      const msg = 'Selecciona uno o más archivos primero.'
      setError(msg)
      toast.warning(msg)
      return
    }
    setUploading(true)
    setError(null)
    try {
      const response = await api.uploadDocumentsBatch(files, 'ask_product,product')
      setUploaded((prev) => [...prev, ...response.documents])
      setFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (response.documents.length) {
        toast.success(`${response.documents.length} archivo(s) procesado(s) exitosamente.`)
      }
      if (response.errors.length) {
        const msg = `Fallaron algunos archivos: ${response.errors.join('; ')}`
        setError(msg)
        toast.error(msg)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la carga de archivos'
      setError(msg)
      toast.error(msg)
    } finally {
      setUploading(false)
    }
  }

  const handleRemoveUploaded = async (id: string) => {
    try {
      await api.deleteDocument(id)
      setUploaded((prev) => prev.filter((doc) => doc.id !== id))
      toast.info('Archivo eliminado correctamente.')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló al eliminar archivo'
      setError(msg)
      toast.error(msg)
    }
  }

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault()
    if (!selected.length) {
      const msg = 'Selecciona al menos una fuente.'
      setError(msg)
      toast.warning(msg)
      return
    }
    if (!query.trim() && !documentIds.length) {
      const msg = 'Escribe una pregunta y/o carga archivos.'
      setError(msg)
      toast.warning(msg)
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const data = await api.askProduct({
        query: query.trim() || 'Responder utilizando los documentos cargados y fuentes conectadas.',
        sources: selected,
        document_ids: documentIds,
      })
      setResult(data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló la consulta'
      setError(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSubmit()
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="CONOCIMIENTO"
        title="Consultar Producto"
        subtitle="Sube documentos, selecciona fuentes en vivo y realiza preguntas. Las respuestas citan evidencias o indican claramente si falta información."
      />



      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card space-y-4">
          <div className="flex items-center gap-2">
            <Paperclip className="h-4 w-4 text-[#002777]" aria-hidden />
            <h2 className="text-lg font-semibold">Cargar archivos (opcional)</h2>
          </div>
          <label
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-blue-200 bg-blue-50/40 px-4 py-6 transition-colors hover:border-[#004497] hover:bg-blue-50/70"
            tabIndex={0}
            aria-label="Elegir archivos para cargar"
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click()
            }}
          >
            <Upload className="mb-2 h-7 w-7 text-[#004497]" aria-hidden />
            <span className="text-sm font-medium text-[#002777]">Arrastra archivos o haz clic para explorar</span>
            <span className="mt-1 text-xs text-[var(--color-ink-muted)]">Soporta múltiples archivos</span>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="sr-only"
              onChange={(event) => handlePickFiles(event.target.files)}
            />
          </label>

          {files.length ? (
            <ul className="space-y-2">
              {files.map((file) => (
                <li key={file.name} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
                  <span className="flex items-center gap-2 truncate">
                    <FileText className="h-4 w-4 shrink-0 text-[#004497]" aria-hidden />
                    {file.name}
                  </span>
                  <button type="button" aria-label={`Quitar ${file.name}`} onClick={() => setFiles((prev) => prev.filter((f) => f.name !== file.name))}>
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          {files.length ? (
            <button type="button" onClick={() => void handleUpload()} disabled={uploading} className="btn-primary w-full disabled:opacity-50">
              {uploading ? 'Cargando…' : `Cargar ${files.length} archivo${files.length > 1 ? 's' : ''}`}
            </button>
          ) : null}

          {uploaded.length ? (
            <ul className="space-y-2 border-t border-[var(--color-border)] pt-3">
              {uploaded.map((doc) => (
                <li key={doc.id} className="flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50/50 px-3 py-2 text-sm">
                  <span className="truncate">{doc.filename}</span>
                  <button type="button" aria-label={`Eliminar ${doc.filename}`} onClick={() => void handleRemoveUploaded(doc.id)}>
                    <Trash2 className="h-4 w-4 text-[var(--color-ink-muted)] hover:text-[var(--color-bad)]" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <form onSubmit={(event) => void handleSubmit(event)} className="card space-y-4">
          <fieldset className="flex flex-wrap gap-3 text-sm">
            <legend className="mb-2 w-full text-sm font-semibold">Fuentes para esta pregunta</legend>
            {SOURCE_OPTIONS.map((option) => (
              <label key={option.id} className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 py-1.5">
                <input
                  type="checkbox"
                  checked={selected.includes(option.id)}
                  onChange={(event) => {
                    setSelected((prev) =>
                      event.target.checked ? [...prev, option.id] : prev.filter((item) => item !== option.id),
                    )
                  }}
                />
                {option.label}
              </label>
            ))}
          </fieldset>

          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={5}
            className="input-field w-full resize-none rounded-xl border border-[var(--color-border)] bg-white px-3 py-2"
            placeholder="¿Cuáles son las reglas de negocio para el flujo de pago?"
            aria-label="Pregunta sobre el producto"
          />

          <button type="submit" disabled={busy} className="btn-primary flex items-center gap-2 disabled:opacity-50">
            <Send className="h-4 w-4" aria-hidden />
            {busy ? 'Buscando…' : 'Consultar'}
          </button>
        </form>
      </div>

      {result ? <GroundedResultView result={result} /> : null}
    </div>
  )
}
