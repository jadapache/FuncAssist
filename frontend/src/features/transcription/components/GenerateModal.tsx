import type React from 'react'
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  X,
  FileSpreadsheet,
  FileText,
  Sparkles,
  Download,
  ExternalLink,
  CheckCircle2,
  Loader2,
  ChevronLeft,
  FileCode,
} from 'lucide-react'
import { inferenceService } from '../../ai/services/InferenceService'
import { transcriptionApi } from '../api/transcriptionApi'
import { api, type CorporateTemplate } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

interface GenerateModalProps {
  isOpen: boolean
  transcriptionId?: string | null
  meetingTitle?: string
  onClose: () => void
}

interface GeneratedDocState {
  templateId: string
  content: string
  title: string
  fileType: string
  module: string
}

export const GenerateModal: React.FC<GenerateModalProps> = ({
  isOpen,
  meetingTitle,
  onClose,
}) => {
  const { toast } = useToast()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<CorporateTemplate[]>([])
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [generatedDoc, setGeneratedDoc] = useState<GeneratedDocState | null>(null)

  useEffect(() => {
    if (!isOpen) return
    let isMounted = true

    const loadTemplates = async () => {
      setIsLoadingTemplates(true)
      try {
        const res = await api.getTemplates()
        if (isMounted) {
          setTemplates(res.templates || [])
        }
      } catch (err: unknown) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : 'Error al cargar plantillas'
          toast.error(`No se pudieron cargar las plantillas: ${msg}`)
        }
      } finally {
        if (isMounted) setIsLoadingTemplates(false)
      }
    }

    void loadTemplates()

    return () => {
      isMounted = false
    }
  }, [isOpen, toast])

  if (!isOpen) return null

  const handleGenerate = async (template: CorporateTemplate) => {
    setSelectedTemplateId(template.id)
    setIsGenerating(true)

    try {
      let templateContent = ''
      try {
        const detail = await api.getTemplateContent(template.id)
        templateContent = detail.content || ''
      } catch {
        // Fallback to title/module prompt if content cannot be read
      }

      const instructions = [
        `Genera el documento corporativo "${template.title}" para el módulo "${template.module}" a partir de la transcripción y contexto de la reunión: ${meetingTitle || ''}.`,
        templateContent ? `\nEstructura y directrices de la plantilla de referencia:\n${templateContent}` : '',
        `\nCompleta todas las secciones requeridas, tablas y criterios funcionales con alto nivel de detalle técnico.`,
      ].filter(Boolean).join('\n')

      const res = await inferenceService.generateArtifact({
        instructions,
        context: meetingTitle ? `Reunión: ${meetingTitle}` : undefined,
      })

      const text = res.content || 'Documento generado con éxito.'
      const docTitle = `${template.title} - ${meetingTitle || 'Reunion'}`

      setGeneratedDoc({
        templateId: template.id,
        content: text,
        title: docTitle,
        fileType: (template.file_type || 'docx').toLowerCase(),
        module: template.module || 'general',
      })
      toast.success(`"${template.title}" generado con IA.`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido'
      toast.error(`Error al generar documento: ${msg}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDownload = async () => {
    if (!generatedDoc) return
    try {
      setIsExporting(true)
      const isXlsx = generatedDoc.fileType.includes('xlsx') || generatedDoc.fileType.includes('excel')
      const blob = isXlsx
        ? await transcriptionApi.exportInventarioXlsx(generatedDoc.content, generatedDoc.title)
        : await transcriptionApi.exportLevantamientoDocx(generatedDoc.content, generatedDoc.title)

      const ext = isXlsx ? 'xlsx' : 'docx'
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${generatedDoc.title.replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success(`Archivo .${ext} descargado con éxito.`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al exportar'
      toast.error(`Error al descargar: ${msg}`)
    } finally {
      setIsExporting(false)
    }
  }

  const handleOpenWorkspace = () => {
    if (!generatedDoc) return
    onClose()
    const targetModule = generatedDoc.module.toLowerCase()
    const path = targetModule === 'inventario'
      ? '/funcional/inventario'
      : targetModule === 'levantamiento'
      ? '/funcional/levantamiento'
      : targetModule === 'mejoras'
      ? '/funcional/mejoras'
      : `/funcional/${targetModule}`
    navigate(path)
  }

  const handleResetToOptions = () => {
    setGeneratedDoc(null)
    setSelectedTemplateId(null)
  }

  const renderTemplateCard = (template: CorporateTemplate) => {
    const isSelected = selectedTemplateId === template.id
    const isCurrentGenerating = isGenerating && isSelected
    const isXlsx = (template.file_type || '').toLowerCase().includes('xlsx')
    const IconComponent = isXlsx ? FileSpreadsheet : FileText
    const formatBadge = isXlsx ? 'Excel (.xlsx)' : 'Word (.docx)'

    return (
      <div
        key={template.id}
        onClick={() => !isGenerating && handleGenerate(template)}
        className={`card p-5 border transition rounded-2xl cursor-pointer flex flex-col justify-between space-y-4 hover:shadow-md ${
          isSelected && isGenerating
            ? 'border-blue-500 bg-blue-50/40 ring-2 ring-blue-500/20'
            : isXlsx
            ? 'border-slate-200 hover:border-blue-400 bg-white'
            : 'border-slate-200 hover:border-emerald-400 bg-white'
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3.5">
            <div
              className={`flex h-11 w-11 items-center justify-center rounded-xl ring-1 shadow-xs ${
                isXlsx
                  ? 'bg-blue-50 text-[#002777] ring-blue-100'
                  : 'bg-emerald-50 text-emerald-700 ring-emerald-100'
              }`}
            >
              <IconComponent className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-slate-900">{template.title}</h4>
                <span
                  className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                    isXlsx
                      ? 'bg-blue-100/70 text-[#002777]'
                      : 'bg-emerald-100/70 text-emerald-800'
                  }`}
                >
                  {formatBadge}
                </span>
                {template.module && (
                  <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[10px] font-medium">
                    {template.module}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">
                {template.tags && template.tags.length > 0
                  ? `Secciones: ${template.tags.slice(0, 4).join(', ')}${template.tags.length > 4 ? '...' : ''}`
                  : `Plantilla corporativa registrada: ${template.filename}`}
              </p>
            </div>
          </div>

          {isCurrentGenerating ? (
            <Loader2 className="h-5 w-5 animate-spin text-[#002777] shrink-0" />
          ) : (
            <Sparkles className="h-5 w-5 text-slate-400 group-hover:text-blue-600 shrink-0" />
          )}
        </div>

        <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
          <span className="text-slate-400 text-[11px]">
            {template.module ? `Módulo: ${template.module}` : 'Plantilla Corporativa'}
          </span>
          <span
            className={`font-bold flex items-center gap-1 ${
              isXlsx ? 'text-[#002777]' : 'text-emerald-700'
            }`}
          >
            {isCurrentGenerating ? 'Generando...' : 'Generar ahora →'}
          </span>
        </div>
      </div>
    )
  }

  const renderContent = () => {
    if (isLoadingTemplates) {
      return (
        <div className="py-12 flex flex-col items-center justify-center space-y-3 text-slate-500">
          <Loader2 className="h-6 w-6 animate-spin text-[#002777]" />
          <span className="text-xs font-medium">Cargando plantillas corporativas...</span>
        </div>
      )
    }

    if (templates.length === 0) {
      return (
        <div className="py-10 px-4 text-center space-y-3 border border-dashed border-slate-200 rounded-2xl bg-slate-50/50">
          <FileCode className="h-8 w-8 text-slate-400 mx-auto" />
          <div className="space-y-1">
            <h4 className="text-sm font-semibold text-slate-700">
              No hay plantillas corporativas registradas
            </h4>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Puedes configurar y subir plantillas desde la sección de Configuración de Plantillas.
            </p>
          </div>
        </div>
      )
    }

    return (
      <div className="grid grid-cols-1 gap-4 pt-1">
        {templates.map(renderTemplateCard)}
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-fade-in">
      <div className="card w-full max-w-2xl max-h-[90vh] bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between px-7 py-5 border-b border-slate-100 shrink-0">
          <div className="flex items-center gap-3">
            {generatedDoc && (
              <button
                type="button"
                onClick={handleResetToOptions}
                className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition"
                title="Volver a selección"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
            )}
            <div>
              <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-[#002777] text-xs font-bold border border-blue-100">
                Generador de Entregables
              </span>
              <h3 className="text-base font-bold text-slate-900 mt-1">
                {generatedDoc
                  ? generatedDoc.title
                  : 'Generar Documentación Funcional con IA'}
              </h3>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition"
            title="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-7 space-y-5 custom-scrollbar">
          {!generatedDoc ? (
            <div className="space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                Selecciona la plantilla corporativa a estructurar a partir del contexto y la transcripción de la reunión.
              </p>
              {renderContent()}
            </div>
          ) : (
            /* Document Preview */
            <div className="space-y-4 animate-fade-in">
              <div className="flex items-center justify-between">
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-bold flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Documento Generado Exitosamente
                </span>
                <span className="text-xs font-semibold text-slate-500">
                  Formato: {generatedDoc.fileType.includes('xlsx') ? 'Excel (.xlsx)' : 'Word (.docx)'}
                </span>
              </div>

              <div className="max-h-80 overflow-y-auto p-4 bg-slate-50 rounded-2xl text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed border border-slate-200 custom-scrollbar">
                {generatedDoc.content}
              </div>
            </div>
          )}
        </div>

        {/* Modal Actions when generated */}
        {generatedDoc && (
          <div className="flex items-center justify-end gap-2.5 px-7 py-4.5 bg-slate-50 border-t border-slate-100 shrink-0">
            <button
              type="button"
              onClick={handleDownload}
              disabled={isExporting}
              className="btn-primary px-4 py-2.5 rounded-xl font-bold flex items-center gap-2 text-xs shadow-md shadow-blue-900/10"
            >
              <Download className="h-3.5 w-3.5" />
              <span>
                {isExporting
                  ? 'Descargando...'
                  : generatedDoc.fileType.includes('xlsx')
                  ? 'Descargar en Excel (.xlsx)'
                  : 'Descargar en Word (.docx)'}
              </span>
            </button>

            <button
              type="button"
              onClick={handleOpenWorkspace}
              className="px-4 py-2.5 bg-blue-50 hover:bg-blue-100 text-[#002777] rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-blue-200"
            >
              <span>Editar en Workspace</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
