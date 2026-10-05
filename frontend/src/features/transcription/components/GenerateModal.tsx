import type React from 'react'
import { useState } from 'react'
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
} from 'lucide-react'
import { api } from '../../../api/client'
import { transcriptionApi } from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'

interface GenerateModalProps {
  isOpen: boolean
  transcriptionId?: string | null
  meetingTitle?: string
  onClose: () => void
}

export const GenerateModal: React.FC<GenerateModalProps> = ({
  isOpen,
  meetingTitle,
  onClose,
}) => {
  const { toast } = useToast()
  const navigate = useNavigate()
  const [selectedDoc, setSelectedDoc] = useState<'inventario' | 'levantamiento' | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [generatedDoc, setGeneratedDoc] = useState<{
    type: 'inventario' | 'levantamiento'
    content: string
    title: string
  } | null>(null)

  if (!isOpen) return null

  const handleGenerate = async (type: 'inventario' | 'levantamiento') => {
    setSelectedDoc(type)
    setIsGenerating(true)

    try {
      const docQuery =
        type === 'inventario'
          ? `Genera el Inventario de Requerimientos y Contexto de Proyecto a partir de la transcripción de la reunión: ${meetingTitle || ''}`
          : `Genera el Levantamiento Detallado de Requerimientos Funcionales, Casos de Uso y Matriz de Trazabilidad a partir de la transcripción de la reunión: ${meetingTitle || ''}`

      const res = await (type === 'inventario'
        ? api.inventarioDoc({ query: docQuery, document_ids: [] })
        : api.levantamientoDoc({ query: docQuery, document_ids: [] }))

      const resObj = res as any
      const text =
        resObj.answer ||
        resObj.answer_clean ||
        resObj.markdown ||
        resObj.reason ||
        'Documento generado con éxito.'

      const docTitle = `${type === 'inventario' ? 'Inventario' : 'Levantamiento'} - ${meetingTitle || 'Reunion'}`

      setGeneratedDoc({
        type,
        content: text,
        title: docTitle,
      })
      toast.success(`${type === 'inventario' ? 'Inventario' : 'Levantamiento'} generado con IA.`)
    } catch (err: any) {
      toast.error(`Error al generar documento: ${err.message}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDownload = async () => {
    if (!generatedDoc) return
    try {
      setIsExporting(true)
      const isInventario = generatedDoc.type === 'inventario'
      const blob = isInventario
        ? await transcriptionApi.exportInventarioXlsx(generatedDoc.content, generatedDoc.title)
        : await transcriptionApi.exportLevantamientoDocx(generatedDoc.content, generatedDoc.title)

      const ext = isInventario ? 'xlsx' : 'docx'
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${generatedDoc.title.replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success(`Archivo .${ext} descargado con éxito.`)
    } catch (err: any) {
      toast.error(`Error al descargar: ${err.message}`)
    } finally {
      setIsExporting(false)
    }
  }

  const handleOpenWorkspace = () => {
    if (!generatedDoc) return
    onClose()
    navigate(`/funcional/${generatedDoc.type}`)
  }

  const handleResetToOptions = () => {
    setGeneratedDoc(null)
    setSelectedDoc(null)
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
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-7 space-y-5 custom-scrollbar">
          {!generatedDoc ? (
            <div className="space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                Selecciona el tipo de documento a estructurar a partir del contexto y la transcripción de la reunión.
              </p>

              {/* Options Cards Grid */}
              <div className="grid grid-cols-1 gap-4 pt-1">
                {/* Option 1: Inventario XLSX */}
                <div
                  onClick={() => !isGenerating && handleGenerate('inventario')}
                  className={`card p-5 border transition rounded-2xl cursor-pointer flex flex-col justify-between space-y-4 hover:shadow-md ${
                    selectedDoc === 'inventario' && isGenerating
                      ? 'border-blue-500 bg-blue-50/40 ring-2 ring-blue-500/20'
                      : 'border-slate-200 hover:border-blue-400 bg-white'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3.5">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-[#002777] ring-1 ring-blue-100 shadow-xs">
                        <FileSpreadsheet className="h-6 w-6 text-[#002777]" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-slate-900">
                            Inventario de Requerimientos (.xlsx)
                          </h4>
                          <span className="px-2 py-0.5 rounded-md bg-blue-100/70 text-[#002777] text-[10px] font-bold">
                            Excel
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed">
                          Visión inicial y catálogo tabular. Consolida antecedentes, stakeholders, objetivos SMART y matriz de requerimientos preliminares (INV-001).
                        </p>
                      </div>
                    </div>

                    {isGenerating && selectedDoc === 'inventario' ? (
                      <Loader2 className="h-5 w-5 animate-spin text-[#002777] shrink-0" />
                    ) : (
                      <Sparkles className="h-5 w-5 text-slate-400 group-hover:text-blue-600 shrink-0" />
                    )}
                  </div>

                  <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
                    <span className="text-slate-400 text-[11px]">Paso 1 Recomendado</span>
                    <span className="font-bold text-[#002777] flex items-center gap-1">
                      {isGenerating && selectedDoc === 'inventario' ? 'Generando...' : 'Generar ahora →'}
                    </span>
                  </div>
                </div>

                {/* Option 2: Levantamiento DOCX */}
                <div
                  onClick={() => !isGenerating && handleGenerate('levantamiento')}
                  className={`card p-5 border transition rounded-2xl cursor-pointer flex flex-col justify-between space-y-4 hover:shadow-md ${
                    selectedDoc === 'levantamiento' && isGenerating
                      ? 'border-emerald-500 bg-emerald-50/40 ring-2 ring-emerald-500/20'
                      : 'border-slate-200 hover:border-emerald-400 bg-white'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3.5">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100 shadow-xs">
                        <FileText className="h-6 w-6 text-emerald-600" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-slate-900">
                            Levantamiento Detallado de Requerimientos (.docx)
                          </h4>
                          <span className="px-2 py-0.5 rounded-md bg-emerald-100/70 text-emerald-800 text-[10px] font-bold">
                            Word
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed">
                          Especificación funcional completa. Detalla requerimientos funcionales con criterios de aceptación (Given-When-Then), User Stories y Casos de Uso.
                        </p>
                      </div>
                    </div>

                    {isGenerating && selectedDoc === 'levantamiento' ? (
                      <Loader2 className="h-5 w-5 animate-spin text-emerald-600 shrink-0" />
                    ) : (
                      <Sparkles className="h-5 w-5 text-slate-400 group-hover:text-emerald-600 shrink-0" />
                    )}
                  </div>

                  <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
                    <span className="text-slate-400 text-[11px]">Paso 2 Detallado</span>
                    <span className="font-bold text-emerald-700 flex items-center gap-1">
                      {isGenerating && selectedDoc === 'levantamiento' ? 'Generando...' : 'Generar ahora →'}
                    </span>
                  </div>
                </div>
              </div>
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
                  Formato: {generatedDoc.type === 'inventario' ? 'Excel (.xlsx)' : 'Word (.docx)'}
                </span>
              </div>

              <div className="max-h-80 overflow-y-auto p-4 bg-slate-50 rounded-2xl text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed border border-slate-200 custom-scrollbar">
                {generatedDoc.content}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-7 py-4.5 bg-slate-50 border-t border-slate-100 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-200/60 rounded-xl transition"
          >
            Cerrar
          </button>

          {generatedDoc && (
            <div className="flex items-center gap-2.5">
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
                    : generatedDoc.type === 'inventario'
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
    </div>
  )
}
