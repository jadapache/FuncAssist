import type React from 'react'
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  X,
  FileSpreadsheet,
  FileText,
  Sparkles,
  Loader2,
  FileCode,
} from 'lucide-react'
import { inferenceService } from '../../ai/services/InferenceService'
import { transcriptionApi } from '../api/transcriptionApi'
import { condenseTranscriptForBrowser } from '../hooks/useTranscriptionActions'
import { api, type CorporateTemplate } from '../../../api/client'
import { draftsApi } from '../../../features/document/api/draftsApi'
import { useToast } from '../../../context/ToastContext'

interface GenerateModalProps {
  isOpen: boolean
  transcriptionId?: string | null
  meetingTitle?: string
  onClose: () => void
}

interface GeneratedDocState {
  title: string
  fileType: string
  module: string
  content: string
  transcriptionContext?: string
}

export const GenerateModal: React.FC<GenerateModalProps> = ({
  isOpen,
  transcriptionId,
  meetingTitle,
  onClose,
}) => {
  const { toast } = useToast()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<CorporateTemplate[]>([])
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false)
  const [processingTemplateId, setProcessingTemplateId] = useState<string | null>(null)

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

  const openWorkspaceWithDoc = async (doc: GeneratedDocState) => {
    const rawModule = (doc.module || 'chat').trim().toLowerCase()
    const targetSlug =
      rawModule === 'inventario'
        ? 'inventario'
        : rawModule === 'levantamiento'
        ? 'levantamiento'
        : 'chat'

    const isXlsx = doc.fileType.includes('xlsx') || doc.fileType.includes('excel')
    const ext = isXlsx ? 'xlsx' : 'docx'
    const newSessionId = crypto.randomUUID()
    const nowIso = new Date().toISOString()

    const newArtifact = {
      id: crypto.randomUUID(),
      title: doc.title,
      extension: ext as 'docx' | 'xlsx' | 'txt',
      content: doc.content,
      createdAt: nowIso,
      updatedAt: nowIso,
    }

    const hasContext = Boolean(doc.transcriptionContext)
    const contextContent = doc.transcriptionContext || ''

    const initialMessages = [
      {
        id: crypto.randomUUID(),
        role: 'user' as const,
        content: `Genera el documento "${doc.title}" estructurado y completo basado en la transcripción de la reunión.`,
        timestamp: nowIso,
        attachments: hasContext
          ? [
              {
                id: crypto.randomUUID(),
                name: 'Transcripción - Contexto de Reunión',
                type: 'file' as const,
                size: contextContent.length,
                content: contextContent,
              },
            ]
          : undefined,
      },
      {
        id: crypto.randomUUID(),
        role: 'assistant' as const,
        content: `He generado el documento "${doc.title}" a partir de la transcripción de la reunión. Puedes revisarlo, editarlo o exportarlo.`,
        timestamp: nowIso,
      },
    ]

    try {
      await draftsApi.saveDraft({
        id: newSessionId,
        name: doc.title,
        title: doc.title,
        feature_slug: targetSlug,
        specification: targetSlug,
        lastInteraction: nowIso,
        messages: initialMessages,
        documentContent: doc.content,
        artifacts: [newArtifact],
      })
    } catch (saveErr) {
      console.warn('No se pudo guardar la sesión de borrador previa:', saveErr)
    }

    onClose()
    navigate(`/funcional/${targetSlug}/${newSessionId}`)
  }

  const buildTranscriptionContext = async (): Promise<string> => {
    if (!transcriptionId) return ''
    try {
      const transResult = await transcriptionApi.getTranscriptionResult(transcriptionId)
      const rawText = transResult.text || ''
      const summary = transResult.summary?.summary_text || ''
      const insights = transResult.summary?.key_insights?.join('\n- ') || ''
      const safeText = condenseTranscriptForBrowser(rawText, 10000)

      const parts = [
        `Título de la Reunión: ${transResult.metadata?.title || meetingTitle || 'Reunión'}`,
        summary ? `Resumen y Acuerdos de la Reunión:\n${summary}` : '',
        insights ? `Puntos Clave y Decisiones:\n- ${insights}` : '',
        safeText ? `Transcripción Relevante de la Discusión:\n${safeText}` : '',
      ].filter(Boolean)

      return parts.join('\n\n')
    } catch (fetchErr) {
      console.warn('No se pudo recuperar la transcripción completa:', fetchErr)
      return ''
    }
  }

  const handleGenerate = async (template: CorporateTemplate) => {
    if (processingTemplateId) return
    setProcessingTemplateId(template.id)

    try {
      let templateContent = ''
      try {
        const detail = await api.getTemplateContent(template.id)
        templateContent = detail.content || ''
      } catch {
        // Fallback si no se puede leer el contenido de la plantilla
      }

      const transcriptionContext = await buildTranscriptionContext()

      const instructions = [
        `Genera el documento corporativo "${template.title}" para el módulo "${template.module}" basándote rigurosamente en la información de la transcripción y el contexto de la reunión.`,
        templateContent ? `\nEstructura y directrices de la plantilla de referencia:\n${templateContent}` : '',
        `\nCompleta todas las secciones requeridas, tablas y criterios funcionales con alto nivel de detalle técnico sin omitir datos provistos.`,
      ].filter(Boolean).join('\n')

      const res = await inferenceService.generateArtifact({
        instructions,
        context: transcriptionContext || (meetingTitle ? `Reunión: ${meetingTitle}` : undefined),
      })

      const text = res.content || 'Documento generado con éxito.'
      const docTitle = `${template.title} - ${meetingTitle || 'Reunion'}`

      await openWorkspaceWithDoc({
        title: docTitle,
        fileType: (template.file_type || 'docx').toLowerCase(),
        module: template.module || 'general',
        content: text,
        transcriptionContext: transcriptionContext || undefined,
      })
      toast.success(`"${template.title}" generado con IA. Redirigiendo al workspace...`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido'
      toast.error(`Error al generar documento: ${msg}`)
    } finally {
      setProcessingTemplateId(null)
    }
  }

  const renderTemplateCard = (template: CorporateTemplate) => {
    const isCurrentProcessing = processingTemplateId === template.id
    const isOtherProcessing = Boolean(processingTemplateId && !isCurrentProcessing)
    const isXlsx = (template.file_type || '').toLowerCase().includes('xlsx')
    const IconComponent = isXlsx ? FileSpreadsheet : FileText
    const formatBadge = isXlsx ? 'Excel (.xlsx)' : 'Word (.docx)'

    let cardBorderBg = isXlsx
      ? 'border-slate-200 hover:border-emerald-400 bg-white cursor-pointer hover:shadow-md'
      : 'border-slate-200 hover:border-blue-400 bg-white cursor-pointer hover:shadow-md'

    if (isCurrentProcessing) {
      cardBorderBg = isXlsx
        ? 'border-emerald-500 bg-emerald-50/40 ring-2 ring-emerald-500/20 cursor-wait'
        : 'border-blue-500 bg-blue-50/40 ring-2 ring-blue-500/20 cursor-wait'
    } else if (isOtherProcessing) {
      cardBorderBg = 'border-slate-200 bg-slate-50/70 opacity-50 cursor-not-allowed pointer-events-none'
    }

    return (
      <button
        key={template.id}
        type="button"
        disabled={Boolean(processingTemplateId)}
        onClick={() => !processingTemplateId && void handleGenerate(template)}
        className={`w-full text-left card p-5 border transition rounded-2xl flex flex-col justify-between space-y-4 ${cardBorderBg}`}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3.5">
            <div
              className={`flex h-11 w-11 items-center justify-center rounded-xl ring-1 shadow-xs ${
                isXlsx
                  ? 'bg-emerald-50 text-emerald-700 ring-emerald-100'
                  : 'bg-blue-50 text-[#002777] ring-blue-100'
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
                      ? 'bg-emerald-100/70 text-emerald-800'
                      : 'bg-blue-100/70 text-[#002777]'
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

          {isCurrentProcessing ? (
            <Loader2
              className={`h-5 w-5 animate-spin shrink-0 ${
                isXlsx ? 'text-emerald-700' : 'text-[#002777]'
              }`}
            />
          ) : (
            <Sparkles
              className={`h-5 w-5 text-slate-400 shrink-0 ${
                isXlsx ? 'group-hover:text-emerald-600' : 'group-hover:text-blue-600'
              }`}
            />
          )}
        </div>

        <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
          <span className="text-slate-400 text-[11px]">
            {template.module ? `Módulo: ${template.module}` : 'Plantilla Corporativa'}
          </span>
          <span
            className={`font-bold flex items-center gap-1 ${
              isXlsx ? 'text-emerald-700' : 'text-[#002777]'
            }`}
          >
            {isCurrentProcessing ? 'Generando y abriendo...' : 'Generar ahora →'}
          </span>
        </div>
      </button>
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
          <div>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-[#002777] text-xs font-bold border border-blue-100">
              Generador de Entregables
            </span>
            <h3 className="text-base font-bold text-slate-900 mt-1">
              Generar Documentación Funcional con IA
            </h3>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={Boolean(processingTemplateId)}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition disabled:opacity-40 disabled:cursor-not-allowed"
            title="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-7 space-y-5 custom-scrollbar">
          <div className="space-y-4">
            <p className="text-xs text-slate-600 leading-relaxed">
              Selecciona la plantilla corporativa a estructurar a partir del contexto y la transcripción de la reunión.
            </p>
            {renderContent()}
          </div>
        </div>
      </div>
    </div>
  )
}
