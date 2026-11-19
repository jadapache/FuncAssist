import { FileText, Download, ExternalLink } from 'lucide-react'
import type { Artifact } from '../../../types/artifacts'
import { API_BASE, getAuthHeaders } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

interface InlineArtifactCardProps {
  artifact: Artifact
  onOpen: (artifact: Artifact) => void
}

export const InlineArtifactCard = ({
  artifact,
  onOpen,
}: InlineArtifactCardProps) => {
  const { toast } = useToast()

  const handleDownload = async () => {
    const { title, content, extension } = artifact

    try {
      if (extension === 'txt') {
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title.replace(/\s+/g, '_')}.txt`
        a.click()
        URL.revokeObjectURL(url)
        toast.success('Documento descargado como .txt')
        return
      }

      const endpoint =
        extension === 'xlsx'
          ? `${API_BASE}/api/doc-agent/export-xlsx`
          : `${API_BASE}/api/doc-agent/export-docx`

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ title, content }),
      })

      if (!response.ok) throw new Error(`Error al exportar .${extension}`)

      const arrayBuffer = await response.arrayBuffer()
      const mimeType =
        extension === 'xlsx'
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

      const blob = new Blob([arrayBuffer], { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${title.replace(/\s+/g, '_')}.${extension}`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`Documento descargado como .${extension}`)
    } catch {
      toast.error('Error al exportar el documento.')
    }
  }

  // Estimar tamaño aproximado basado en caracteres
  const formatApproxSize = (text: string) => {
    const bytes = new Blob([text]).size
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="my-2.5 flex items-center justify-between gap-3 rounded-2xl border border-blue-100 bg-blue-50/60 p-3.5 shadow-2xs transition-all hover:bg-blue-50/90">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
          <FileText className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="text-xs font-bold text-slate-900 truncate" title={artifact.title}>
            {artifact.title}
          </h4>
          <p className="text-[11px] text-slate-500 truncate mt-0.5">
            {artifact.extension === 'xlsx' ? 'Hoja de Cálculo' : 'Documento'} •{' '}
            {formatApproxSize(artifact.content)}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={handleDownload}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-slate-900 transition cursor-pointer"
          title="Descargar documento"
        >
          <Download className="h-3.5 w-3.5 text-slate-500" />
          <span>Descargar</span>
        </button>

        <button
          type="button"
          onClick={() => onOpen(artifact)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-[#001744] px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-[#002777] transition cursor-pointer"
          title="Abrir documento en vista detallada"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          <span>Abrir</span>
        </button>
      </div>
    </div>
  )
}

export default InlineArtifactCard
