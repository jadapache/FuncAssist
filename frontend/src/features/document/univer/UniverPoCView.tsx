import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  FileText,
  FileSpreadsheet,
  Sparkles,
} from 'lucide-react'
import { UniverAdapter } from '../../../features/document/agent/adapters/UniverAdapter'
import { DocumentAgent } from '../../../features/document/agent/core/DocumentAgent'
import type {
  CanonicalDocumentOperation,
  CanonicalDocumentState,
} from '../../../features/document/agent/core/types'
import { UniverContainer } from './UniverContainer'
import { DocumentChatBar, type AgenticStep } from './DocumentChatBar'
import { DocumentInspectorModal } from './DocumentInspectorModal'
import { useToast } from '../../../context/ToastContext'

const DEFAULT_DOCX_FIXTURE = `# DOCUMENTO DE ESPECIFICACIÓN DE MEJORA FUNCIONAL

## 1. NECESIDAD IDENTIFICADA
Actualmente los usuarios del módulo de admisiones no disponen de validación en tiempo real al subir documentos soporte. Se requiere implementar un motor de validación previa que reduzca las devoluciones de solicitudes por inconsistencias documentales.

{{NECESIDAD}}

## 2. IMPACTO EN EL NEGOCIO
- Reducción del 45% en los tiempos de respuesta al paciente.
- Eliminación de reprocesos manuales por parte del equipo asistencial.
- Auditoría automatizada de los soportes cargados.

{{IMPACTO}}

## 3. SOLUCIÓN PROPUESTA
Se integrará un componente de escaneo asistido con visión artificial y reglas de negocio parametrizables para verificar legibilidad y completitud de firmas antes del envío definitivo.

{{SOLUCION}}

## 4. OBSERVACIONES Y CASOS DE BORDE
En casos donde la conectividad sea inestable, el documento se almacenará en cola offline local encriptada hasta restablecer sincronización con el servidor central.

{{OBSERVACIONES}}

## 5. FIRMAS Y RESPONSABLES
| Rol | Nombre | Estado |
| Responsable QA | Ing. Daniel Pacheco | Aprobado |
| Líder Funcional | Coordinación Médica | En Revisión |

{{FIRMAS}}
`

const DEFAULT_XLSX_FIXTURE = `# MATRIZ DE PRUEBAS Y ESTIMACIÓN QA
| ID | Caso de Prueba | Requerimiento | Estado | Severidad |
| TC01 | Validación de Login | REQ-01 | Aprobado | Alta |
| TC02 | Bloqueo de Cuenta | REQ-01 | Pendiente | Crítica |
| TC03 | Carga de Archivos | REQ-02 | Aprobado | Media |
`

export const UniverPoCView = () => {
  const { toast } = useToast()

  // Engine & Agent instances
  const adapter = useMemo(() => new UniverAdapter('document'), [])
  const agent = useMemo(() => new DocumentAgent(adapter), [adapter])

  // State
  const [selectedFixture, setSelectedFixture] = useState<'docx' | 'xlsx'>('docx')
  const [title, setTitle] = useState('Propuesta de Mejora Funcional (Plantilla HIC)')
  const [content, setContent] = useState(DEFAULT_DOCX_FIXTURE)
  const [images, setImages] = useState<Array<{ id: string; sectionId: string; url: string; caption?: string }>>([])

  // Modal & Inspector
  const [isInspectorOpen, setIsInspectorOpen] = useState(false)
  const [canonicalState, setCanonicalState] = useState<CanonicalDocumentState | null>(null)

  // Agentic RAG chat execution
  const [loading, setLoading] = useState(false)
  const [currentSteps, setCurrentSteps] = useState<AgenticStep[]>([])
  const [lastFeedback, setLastFeedback] = useState<string | null>(null)

  // Initialize fixture into adapter
  const loadFixture = useCallback(
    async (kind: 'docx' | 'xlsx') => {
      const fixtureContent = kind === 'docx' ? DEFAULT_DOCX_FIXTURE : DEFAULT_XLSX_FIXTURE
      const fixtureTitle =
        kind === 'docx'
          ? 'Propuesta de Mejora Funcional (Plantilla HIC)'
          : 'Matriz de Casos de Prueba y Estimación'

      setSelectedFixture(kind)
      setTitle(fixtureTitle)
      setContent(fixtureContent)
      setImages([])
      setLastFeedback(null)
      setCurrentSteps([])

      await adapter.loadTemplate(fixtureContent, kind === 'docx' ? 'document' : 'spreadsheet', fixtureTitle)
      const inspected = await agent.inspect()
      setCanonicalState(inspected)
    },
    [adapter, agent]
  )

  useEffect(() => {
    void loadFixture('docx')
  }, [loadFixture])

  // Open canonical inspector
  const handleOpenInspector = async () => {
    const inspected = await agent.inspect()
    setCanonicalState(inspected)
    setIsInspectorOpen(true)
  }

  // Handle Export
  const handleExport = async (format: 'docx' | 'xlsx' | 'json') => {
    try {
      if (format === 'json') {
        const state = await agent.inspect()
        const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title.replace(/\s+/g, '_')}_canonical.json`
        a.click()
        URL.revokeObjectURL(url)
        return
      }

      const endpoint = format === 'docx' ? '/api/doc-agent/export-docx' : '/api/doc-agent/export-xlsx'
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          content: adapter.getRawContent(),
        }),
      })

      if (!response.ok) {
        throw new Error(`Error del servidor al exportar ${format}`)
      }

      const arrayBuffer = await response.arrayBuffer()
      const mimeType =
        format === 'docx'
          ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
          : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

      const blob = new Blob([arrayBuffer], { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${title.replace(/\s+/g, '_')}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      toast.error('Error al exportar el documento.')
    }
  }

  // Send message through the complete Agentic RAG + DocumentAgent cycle
  const handleSendMessage = async (prompt: string, attachedAssetIds: string[]) => {
    setLoading(true)
    setLastFeedback(null)

    // Step 1: INSPECT
    const steps: AgenticStep[] = [
      { id: 'inspect', label: '1. INSPECT', status: 'in_progress', details: 'Leyendo estado canónico del documento...' },
      { id: 'rag', label: '2. RAG & PLAN', status: 'pending', details: 'Consultando intención y base de conocimiento...' },
      { id: 'validate', label: '3. VALIDATE', status: 'pending', details: 'Verificando targets, assets y permisos...' },
      { id: 'execute', label: '4. EXECUTE', status: 'pending', details: 'Traduciendo a comandos de Univer...' },
      { id: 'verify', label: '5. VERIFY', status: 'pending', details: 'Auditoría delta post-mutación...' },
    ]
    setCurrentSteps([...steps])

    try {
      // 1. Inspect current document state
      const stateBefore = await agent.inspect()
      setCanonicalState(stateBefore)
      steps[0].status = 'completed'
      steps[0].details = `Identificadas ${stateBefore.sections.length} secciones (Observaciones localizada)`
      steps[1].status = 'in_progress'
      setCurrentSteps([...steps])

      // 2. Call FastAPI Backend Agentic RAG endpoint
      const response = await fetch('/api/doc-agent/agentic-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          document_state: stateBefore,
          documentState: stateBefore,
          attached_asset_ids: attachedAssetIds,
          attachedAssetIds: attachedAssetIds,
        }),
      })

      if (!response.ok) {
        let errorDetails = response.statusText
        try {
          const errJson = await response.json()
          errorDetails = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail || errJson)
        } catch {
          // ignore
        }
        throw new Error(`Error en orquestador de agente (${response.status}): ${errorDetails}`)
      }

      const agentData = await response.json()
      const intent = agentData.intentDetected ?? agentData.intent_detected ?? 'Operación identificada'
      const plannedOps: CanonicalDocumentOperation[] =
        agentData.plannedOperations ?? agentData.planned_operations ?? []
      const requiresMutation =
        agentData.requiresDocumentMutation ?? agentData.requires_document_mutation ?? (plannedOps.length > 0)
      const assistantMessage =
        agentData.assistantMessage ?? agentData.assistant_message ?? 'Operación procesada con éxito.'

      steps[1].status = 'completed'
      steps[1].details = `Intención: "${intent}" (${plannedOps.length} ops)`
      steps[2].status = 'in_progress'
      setCurrentSteps([...steps])

      if (!requiresMutation || plannedOps.length === 0) {
        steps[2].status = 'completed'
        steps[2].details = 'No requiere mutación documental'
        steps[3].status = 'completed'
        steps[3].details = 'Omitido'
        steps[4].status = 'completed'
        steps[4].details = 'Verificado'
        setCurrentSteps([...steps])
        setLastFeedback(assistantMessage)
        setLoading(false)
        return
      }

      // 3. VALIDATE locally using DocumentAgent
      const operations = plannedOps

      for (const op of operations) {
        const val = await agent.validate(op, stateBefore)
        if (!val.valid) {
          throw new Error(`Fallo de validación: ${val.reason}`)
        }
      }
      steps[2].status = 'completed'
      steps[2].details = 'Targets, assets y políticas validadas'
      steps[3].status = 'in_progress'
      setCurrentSteps([...steps])

      // 4. EXECUTE operations through UniverAdapter
      for (const op of operations) {
        await agent.dispatch(op)
      }
      steps[3].status = 'completed'
      steps[3].details = `Ejecutadas ${operations.length} operaciones en Univer`
      steps[4].status = 'in_progress'
      setCurrentSteps([...steps])

      // 5. VERIFY post-mutation state
      const stateAfter = await agent.inspect()
      setCanonicalState(stateAfter)
      setContent(adapter.getRawContent())
      setImages(adapter.getImages())

      steps[4].status = 'completed'
      steps[4].details = `Verificado: +${stateAfter.totalImages - stateBefore.totalImages} imágenes añadidas`
      setCurrentSteps([...steps])

      setLastFeedback(assistantMessage)
    } catch (err) {
      console.error(err)
      const errorMsg = err instanceof Error ? err.message : 'Error al procesar la instrucción del agente.'
      const currentIdx = steps.findIndex((s) => s.status === 'in_progress')
      if (currentIdx !== -1) {
        steps[currentIdx].status = 'failed'
        steps[currentIdx].details = errorMsg
      }
      setCurrentSteps([...steps])
      setLastFeedback(`Error: ${errorMsg}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-slate-50 overflow-hidden">
      {/* Top Banner: PoC Status & Fixture Switcher */}
      <div className="bg-white border-b border-slate-200 px-6 py-3 flex flex-wrap items-center justify-between gap-4 shrink-0 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-600 text-white rounded-xl shadow-xs">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-slate-900 text-base">PoC Univer • Document Engine & Agentic RAG</h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300">
                PoC Activa
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Evaluación del motor documental desacoplado mediante <span className="font-mono font-semibold text-indigo-600">DocumentAgent</span> y ciclo <span className="font-semibold text-slate-700">Inspect-Plan-Execute-Verify</span>.
            </p>
          </div>
        </div>

        {/* Fixture Selector (DOCX vs XLSX) */}
        <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl border border-slate-200">
          <button
            type="button"
            onClick={() => loadFixture('docx')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              selectedFixture === 'docx'
                ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/80'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileText className="h-4 w-4" />
            <span>Fixture DOCX (Mejoras)</span>
          </button>
          <button
            type="button"
            onClick={() => loadFixture('xlsx')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              selectedFixture === 'xlsx'
                ? 'bg-white text-emerald-700 shadow-xs border border-slate-200/80'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileSpreadsheet className="h-4 w-4" />
            <span>Fixture XLSX (Casos de Prueba)</span>
          </button>
        </div>
      </div>

      {/* Main Workspace: Univer Container */}
      <div className="flex-1 p-4 overflow-hidden flex flex-col min-h-0">
        <UniverContainer
          adapter={adapter}
          kind={selectedFixture === 'docx' ? 'document' : 'spreadsheet'}
          title={title}
          content={content}
          images={images}
          onInspect={handleOpenInspector}
          onExport={handleExport}
          onReloadFixture={() => loadFixture(selectedFixture)}
        />
      </div>

      {/* Docked Agentic RAG Chat & Intent Execution Bar */}
      <div className="shrink-0">
        <DocumentChatBar
          onSendMessage={handleSendMessage}
          loading={loading}
          currentSteps={currentSteps}
          lastFeedback={lastFeedback}
        />
      </div>

      {/* Canonical Inspector Modal */}
      <DocumentInspectorModal
        state={canonicalState}
        isOpen={isInspectorOpen}
        onClose={() => setIsInspectorOpen(false)}
      />
    </div>
  )
}
