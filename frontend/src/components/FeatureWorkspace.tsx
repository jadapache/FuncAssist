import type { FormEvent, KeyboardEvent } from 'react'
import { useRef, useState } from 'react'
import { FileText, Paperclip, Send, Trash2, Upload, X } from 'lucide-react'
import { api, type GroundedResult, type KnowledgeDocument } from '../api/client'
import { GroundedResultView } from '../pages/pm/StandupPage'
import { PageHeader } from './common'
import { useToast } from '../context/ToastContext'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

type SourceOption = {
  id: string
  label: string
}

type FeatureWorkspaceProps = {
  eyebrow: string
  title: string
  description: string
  uploadTags: string
  placeholder: string
  defaultQuery: string
  showSourceToggles?: boolean
  sourceOptions?: SourceOption[]
  defaultSources?: string[]
  onRun: (payload: {
    query: string
    documentIds: string[]
    chatContext: string
    sources: string[]
  }) => Promise<GroundedResult>
}

const ACCEPT = '.pdf,.docx,.md,.txt,.json'

export const FeatureWorkspace = ({
  eyebrow,
  title,
  description,
  uploadTags,
  placeholder,
  defaultQuery,
  showSourceToggles = false,
  sourceOptions = [],
  defaultSources = [],
  onRun,
}: FeatureWorkspaceProps) => {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [uploaded, setUploaded] = useState<KnowledgeDocument[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [selectedSources, setSelectedSources] = useState<string[]>(defaultSources)
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

  const handleRemovePending = (name: string) => {
    setFiles((prev) => prev.filter((file) => file.name !== name))
  }

  const handleRemoveUploaded = async (id: string) => {
    setError(null)
    try {
      await api.deleteDocument(id)
      setUploaded((prev) => prev.filter((doc) => doc.id !== id))
      toast.info('Archivo eliminado correctamente.')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló al eliminar el archivo'
      setError(msg)
      toast.error(msg)
    }
  }

  const handleUpload = async () => {
    if (!files.length) {
      const msg = 'Selecciona uno o más archivos para cargar.'
      setError(msg)
      toast.warning(msg)
      return
    }
    setUploading(true)
    setError(null)
    try {
      const response = await api.uploadDocumentsBatch(files, uploadTags)
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
      const msg = err instanceof Error ? err.message : 'Falló la carga'
      setError(msg)
      toast.error(msg)
    } finally {
      setUploading(false)
    }
  }

  const buildChatContext = (extra?: string) => {
    const lines = messages.map((msg) => `${msg.role === 'user' ? 'Usuario' : 'Asistente'}: ${msg.content}`)
    if (extra?.trim()) lines.push(`Usuario: ${extra.trim()}`)
    return lines.join('\n')
  }

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault()
    const text = draft.trim()
    if (!text && !documentIds.length) {
      const msg = 'Sube archivos y/o escribe instrucciones en el chat.'
      setError(msg)
      toast.warning(msg)
      return
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text || defaultQuery,
    }
    const nextMessages = text ? [...messages, userMessage] : messages
    if (text) setMessages(nextMessages)
    setDraft('')
    setBusy(true)
    setError(null)
    setResult(null)

    try {
      const data = await onRun({
        query: text || defaultQuery,
        documentIds,
        chatContext: buildChatContext(),
        sources: selectedSources,
      })
      setResult(data)
      if (data.answer) {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: 'assistant', content: data.answer ?? '' },
        ])
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falló el análisis'
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
        eyebrow={eyebrow}
        title={title}
        subtitle={description}
      />



      <div className="grid gap-6 lg:grid-cols-2">
        {/* Files panel */}
        <section className="card space-y-4">
          <div className="flex items-center gap-2">
            <Paperclip className="h-4 w-4 text-[#002777]" aria-hidden />
            <h2 className="text-lg font-semibold">Cargar archivos</h2>
          </div>
          <p className="text-sm text-[var(--color-ink-muted)]">
            Selecciona múltiples PRDs, especificaciones o documentos de cambios. Soportados: PDF, DOCX, MD, TXT.
          </p>

          <label
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-blue-200 bg-blue-50/40 px-4 py-8 transition-colors hover:border-[#004497] hover:bg-blue-50/70"
            tabIndex={0}
            aria-label="Elegir archivos para cargar"
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click()
            }}
          >
            <Upload className="mb-2 h-8 w-8 text-[#004497]" aria-hidden />
            <span className="text-sm font-medium text-[#002777]">Arrastra archivos o haz clic para explorar</span>
            <span className="mt-1 text-xs text-[var(--color-ink-muted)]">Se permiten múltiples archivos</span>
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
                <li
                  key={file.name}
                  className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2 truncate">
                    <FileText className="h-4 w-4 shrink-0 text-[#004497]" aria-hidden />
                    {file.name}
                  </span>
                  <button
                    type="button"
                    className="text-[var(--color-ink-muted)] hover:text-[var(--color-bad)]"
                    aria-label={`Quitar ${file.name}`}
                    onClick={() => handleRemovePending(file.name)}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          {files.length ? (
            <button
              type="button"
              onClick={() => void handleUpload()}
              disabled={uploading}
              className="btn-primary w-full disabled:opacity-50"
            >
              {uploading ? 'Cargando…' : `Cargar ${files.length} archivo${files.length > 1 ? 's' : ''}`}
            </button>
          ) : null}

          {uploaded.length ? (
            <div className="space-y-2 border-t border-[var(--color-border)] pt-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-muted)]">
                Listos ({uploaded.length})
              </p>
              <ul className="space-y-2">
                {uploaded.map((doc) => (
                  <li
                    key={doc.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50/50 px-3 py-2 text-sm"
                  >
                    <span className="truncate font-medium">{doc.filename}</span>
                    <button
                      type="button"
                      className="text-[var(--color-ink-muted)] hover:text-[var(--color-bad)]"
                      aria-label={`Eliminar ${doc.filename}`}
                      onClick={() => void handleRemoveUploaded(doc.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>

        {/* Chat panel */}
        <section className="card flex min-h-[420px] flex-col">
          <div className="flex items-center gap-2">
            <Send className="h-4 w-4 text-[#002777]" aria-hidden />
            <h2 className="text-lg font-semibold">Chat de contexto</h2>
          </div>
          <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
            Agrega instrucciones, restricciones o preguntas. Presiona Enter para enviar, Shift+Enter para nueva línea.
          </p>

          {showSourceToggles && sourceOptions.length ? (
            <fieldset className="mt-4 flex flex-wrap gap-3 text-sm">
              <legend className="mb-1 w-full text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-muted)]">
                Fuentes en vivo
              </legend>
              {sourceOptions.map((option) => (
                <label key={option.id} className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 py-1.5">
                  <input
                    type="checkbox"
                    checked={selectedSources.includes(option.id)}
                    onChange={(event) => {
                      setSelectedSources((prev) =>
                        event.target.checked
                          ? [...prev, option.id]
                          : prev.filter((item) => item !== option.id),
                      )
                    }}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
          ) : null}

          <div className="mt-4 flex-1 space-y-3 overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3">
            {messages.length === 0 ? (
              <p className="text-sm text-[var(--color-ink-muted)]">
                Ejemplo: &ldquo;{placeholder}&rdquo;
              </p>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={[
                    'max-w-[95%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap',
                    msg.role === 'user'
                      ? 'ml-auto bg-[#002777] text-white'
                      : 'mr-auto border border-[var(--color-border)] bg-white text-[var(--color-ink)]',
                  ].join(' ')}
                >
                  {msg.content}
                </div>
              ))
            )}
          </div>

          <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 flex gap-2">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder={placeholder}
              className="input-field min-h-[44px] flex-1 resize-none rounded-xl border border-[var(--color-border)] bg-white px-3 py-2"
              aria-label="Mensaje de chat"
            />
            <button
              type="submit"
              disabled={busy}
              className="btn-primary flex shrink-0 items-center gap-2 self-end px-4 disabled:opacity-50"
              aria-label="Enviar mensaje"
            >
              <Send className="h-4 w-4" aria-hidden />
              {busy ? '…' : 'Enviar'}
            </button>
          </form>
        </section>
      </div>

      {result ? <GroundedResultView result={result} /> : null}
    </div>
  )
}
