import type { FormEvent } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Copy,
  FileCode,
  FileText,
  ListOrdered,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Sparkles,
  Trash2,
  Zap,
} from 'lucide-react'
import {
  api,
  type AIPromptTemplate,
  type AIRubric,
} from '../../api/client'
import { useToast } from '../../context/ToastContext'

interface FeatureMeta {
  id: string
  title: string
  description: string
  category: 'workspace' | 'qa' | 'product'
}

const FEATURE_METAS: FeatureMeta[] = [
  {
    id: 'mejoras_doc',
    title: 'Redacción y Mejoras de Documentos',
    description: 'Instrucciones del agente de redacción para propuestas de mejora funcional en formato corporativo.',
    category: 'workspace',
  },
  {
    id: 'standup',
    title: 'Asistente de Standup Diario',
    description: 'Estructuración de resúmenes diarios (Ayer, Hoy, Bloqueos, Riesgos) basados en tickets y PRs.',
    category: 'product',
  },
  {
    id: 'ask_product',
    title: 'Preguntas de Producto y QA',
    description: 'Respuestas a consultas funcionales sustentadas estrictamente en la base de conocimiento.',
    category: 'product',
  },
  {
    id: 'prd_checker',
    title: 'Auditoría de PRDs y Especificaciones',
    description: 'Revisión y análisis de completitud, riesgos y criterios de aceptación en especificaciones.',
    category: 'product',
  },
  {
    id: 'change_impact',
    title: 'Análisis de Impacto de Cambios',
    description: 'Identificación de áreas afectadas, documentación, tickets y partes interesadas por un cambio.',
    category: 'qa',
  },
  {
    id: 'regression',
    title: 'Estrategia de Pruebas de Regresión',
    description: 'Definición de alcance y flujos prioritarios de pruebas basados en historias y cambios recientes.',
    category: 'qa',
  },
  {
    id: 'api_qa',
    title: 'Cobertura y Pruebas de APIs',
    description: 'Detección de endpoints sin probar, escenarios negativos y verificaciones de autenticación.',
    category: 'qa',
  },
  {
    id: 'visual_qa',
    title: 'Checklist de QA Visual y UI',
    description: 'Pautas de verificación de estados de interfaz, accesibilidad y criterios de diseño.',
    category: 'qa',
  },
  {
    id: 'smart_test_data',
    title: 'Generación de Datos de Prueba',
    description: 'Construcción de casos válidos, límites e inválidos respetando reglas de negocio y esquemas.',
    category: 'qa',
  },
  {
    id: 'release_readiness',
    title: 'Evaluación de Salida a Producción',
    description: 'Semáforo de pase a producción verificando bloqueos abiertos, PRs pendientes y riesgos.',
    category: 'qa',
  },
  {
    id: 'transcript_summary',
    title: 'Resumen de Transcripción y Minutas',
    description: 'Generación de resumen narrativo ejecutivo y Key Insights a partir de audios transcritos.',
    category: 'workspace',
  },
  {
    id: 'inventario_doc',
    title: 'Inventario de Requerimientos',
    description: 'Plantilla y rúbrica para generación de matriz de contexto de proyecto e inventario funcional.',
    category: 'product',
  },
  {
    id: 'levantamiento_doc',
    title: 'Levantamiento Detallado de Requerimientos',
    description: 'Plantilla y rúbrica para especificación funcional detallada, historias de usuario y casos de uso.',
    category: 'product',
  },
]

const AVAILABLE_SOURCES = [
  { id: 'knowledge', label: 'Base de Conocimiento (Archivos subidos)' },
  { id: 'jira', label: 'Jira Software' },
  { id: 'github', label: 'GitHub' },
  { id: 'gitlab', label: 'GitLab' },
]

export const AiPromptsRubricsEditor = () => {
  const { toast } = useToast()

  const [selectedFeature, setSelectedFeature] = useState<string>('mejoras_doc')
  const [activeDocType, setActiveDocType] = useState<'prompt' | 'rubric'>('prompt')
  const [editMode, setEditMode] = useState<'form' | 'json'>('form')

  const [promptsList, setPromptsList] = useState<AIPromptTemplate[]>([])
  const [rubricsList, setRubricsList] = useState<AIRubric[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [saving, setSaving] = useState<boolean>(false)
  const [resetting, setResetting] = useState<boolean>(false)

  // Current working prompt / rubric state
  const [promptData, setPromptData] = useState<AIPromptTemplate | null>(null)
  const [rubricData, setRubricData] = useState<AIRubric | null>(null)

  // Raw JSON state for the code editor
  const [rawJsonText, setRawJsonText] = useState<string>('')
  const [jsonError, setJsonError] = useState<string | null>(null)

  // Search filter for features list
  const [searchQuery, setSearchQuery] = useState<string>('')

  // New criterion input in rubric form mode
  const [newCriterion, setNewCriterion] = useState<string>('')

  // Fetch all prompts and rubrics from backend
  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [promptsRes, rubricsRes] = await Promise.all([
        api.getAiPrompts(),
        api.getAiRubrics(),
      ])
      setPromptsList(promptsRes.prompts || [])
      setRubricsList(rubricsRes.rubrics || [])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al cargar reglas y prompts')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  // Sync current selection
  useEffect(() => {
    const curP = promptsList.find((p) => p.feature === selectedFeature) || null
    const curR = rubricsList.find((r) => r.feature === selectedFeature) || null

    setPromptData(curP ? JSON.parse(JSON.stringify(curP)) : null)
    setRubricData(curR ? JSON.parse(JSON.stringify(curR)) : null)

    const targetObj = activeDocType === 'prompt' ? curP : curR
    if (targetObj) {
      setRawJsonText(JSON.stringify(targetObj, null, 2))
      setJsonError(null)
    } else {
      setRawJsonText('')
    }
  }, [selectedFeature, activeDocType, promptsList, rubricsList])

  // Validate raw JSON whenever user types in JSON mode
  const handleRawJsonChange = (text: string) => {
    setRawJsonText(text)
    try {
      const parsed = JSON.parse(text)
      setJsonError(null)
      if (activeDocType === 'prompt') {
        setPromptData(parsed)
      } else {
        setRubricData(parsed)
      }
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Error de sintaxis JSON')
    }
  }

  // Prettify raw JSON
  const handlePrettifyJson = () => {
    try {
      const parsed = JSON.parse(rawJsonText)
      setRawJsonText(JSON.stringify(parsed, null, 2))
      setJsonError(null)
      toast.success('JSON formateado correctamente')
    } catch (e) {
      toast.error('Corrige los errores de sintaxis antes de formatear')
    }
  }

  // Copy to clipboard
  const handleCopyJson = () => {
    void navigator.clipboard.writeText(rawJsonText)
    toast.success('JSON copiado al portapapeles')
  }

  // Switch between form and json mode cleanly
  const handleSwitchMode = (mode: 'form' | 'json') => {
    if (mode === 'json') {
      const targetObj = activeDocType === 'prompt' ? promptData : rubricData
      setRawJsonText(JSON.stringify(targetObj, null, 2))
      setJsonError(null)
    } else {
      if (jsonError) {
        toast.error('Corrige el JSON antes de volver a la vista de formulario')
        return
      }
      try {
        const parsed = JSON.parse(rawJsonText)
        if (activeDocType === 'prompt') {
          setPromptData(parsed)
        } else {
          setRubricData(parsed)
        }
      } catch {
        // ignore
      }
    }
    setEditMode(mode)
  }

  // Switch active document type (prompt vs rubric)
  const handleDocTypeSwitch = (type: 'prompt' | 'rubric') => {
    setActiveDocType(type)
    const targetObj = type === 'prompt' ? promptData : rubricData
    if (targetObj) {
      setRawJsonText(JSON.stringify(targetObj, null, 2))
      setJsonError(null)
    }
  }

  // Save changes
  const handleSave = async () => {
    if (editMode === 'json' && jsonError) {
      toast.error('No se puede guardar: el código contiene errores de sintaxis JSON')
      return
    }

    setSaving(true)
    try {
      if (activeDocType === 'prompt') {
        let payloadToSave = promptData
        if (editMode === 'json') {
          payloadToSave = JSON.parse(rawJsonText)
        }
        if (!payloadToSave) throw new Error('No hay datos de prompt para guardar')

        const saved = await api.updateAiPrompt(selectedFeature, payloadToSave)
        setPromptData(saved)
        setPromptsList((prev) => prev.map((p) => (p.feature === selectedFeature ? saved : p)))
        setRawJsonText(JSON.stringify(saved, null, 2))
        toast.success(`Prompt "${selectedFeature}.json" guardado (Versión v${saved.version})`)
      } else {
        let payloadToSave = rubricData
        if (editMode === 'json') {
          payloadToSave = JSON.parse(rawJsonText)
        }
        if (!payloadToSave) throw new Error('No hay datos de rúbrica para guardar')

        const saved = await api.updateAiRubric(selectedFeature, {
          ...payloadToSave,
          criteria: payloadToSave.criteria || [],
        })
        setRubricData(saved)
        setRubricsList((prev) => prev.map((r) => (r.feature === selectedFeature ? saved : r)))
        setRawJsonText(JSON.stringify(saved, null, 2))
        toast.success(`Rúbrica "${selectedFeature}.json" guardada (Versión v${saved.version})`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar cambios')
    } finally {
      setSaving(false)
    }
  }

  // Reset to default template / rubric
  const handleReset = async () => {
    const docName = activeDocType === 'prompt' ? 'el prompt' : 'la rúbrica'
    if (
      !window.confirm(
        `¿Estás seguro de restablecer ${docName} de "${selectedFeature}" a su contenido predeterminado del sistema? Se perderán las modificaciones personalizadas.`,
      )
    ) {
      return
    }

    setResetting(true)
    try {
      if (activeDocType === 'prompt') {
        const resetRes = await api.resetAiPrompt(selectedFeature)
        setPromptData(resetRes)
        setPromptsList((prev) => prev.map((p) => (p.feature === selectedFeature ? resetRes : p)))
        setRawJsonText(JSON.stringify(resetRes, null, 2))
        toast.success(`Prompt "${selectedFeature}.json" restablecido a los valores predeterminados`)
      } else {
        const resetRes = await api.resetAiRubric(selectedFeature)
        setRubricData(resetRes)
        setRubricsList((prev) => prev.map((r) => (r.feature === selectedFeature ? resetRes : r)))
        setRawJsonText(JSON.stringify(resetRes, null, 2))
        toast.success(`Rúbrica "${selectedFeature}.json" restablecida a los valores predeterminados`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al restablecer valores')
    } finally {
      setResetting(false)
    }
  }

  // Helper to insert placeholders into prompt user_template
  const insertTemplateVariable = (varName: string) => {
    if (!promptData) return
    const placeholder = `{${varName}}`
    const updated = `${promptData.user_template || ''}\n${placeholder}`
    setPromptData({ ...promptData, user_template: updated })
    setRawJsonText(JSON.stringify({ ...promptData, user_template: updated }, null, 2))
    toast.success(`Variable ${placeholder} agregada`)
  }

  // Source checkbox toggle
  const handleToggleSource = (sourceId: string) => {
    if (!promptData) return
    const current = promptData.allowed_sources || []
    const updated = current.includes(sourceId)
      ? current.filter((s) => s !== sourceId)
      : [...current, sourceId]
    const updatedObj = { ...promptData, allowed_sources: updated }
    setPromptData(updatedObj)
    setRawJsonText(JSON.stringify(updatedObj, null, 2))
  }

  // Rubric criteria methods
  const handleAddCriterion = (e: FormEvent) => {
    e.preventDefault()
    if (!newCriterion.trim() || !rubricData) return
    const updatedCriteria = [...(rubricData.criteria || []), newCriterion.trim()]
    const updatedObj = { ...rubricData, criteria: updatedCriteria }
    setRubricData(updatedObj)
    setRawJsonText(JSON.stringify(updatedObj, null, 2))
    setNewCriterion('')
    toast.success('Criterio añadido a la rúbrica')
  }

  const handleDeleteCriterion = (index: number) => {
    if (!rubricData) return
    const updatedCriteria = (rubricData.criteria || []).filter((_, idx) => idx !== index)
    const updatedObj = { ...rubricData, criteria: updatedCriteria }
    setRubricData(updatedObj)
    setRawJsonText(JSON.stringify(updatedObj, null, 2))
  }

  const handleUpdateCriterion = (index: number, val: string) => {
    if (!rubricData) return
    const updatedCriteria = [...(rubricData.criteria || [])]
    updatedCriteria[index] = val
    const updatedObj = { ...rubricData, criteria: updatedCriteria }
    setRubricData(updatedObj)
    setRawJsonText(JSON.stringify(updatedObj, null, 2))
  }

  const allFeatures = useMemo(() => {
    const list: FeatureMeta[] = [...FEATURE_METAS]
    const existingIds = new Set(list.map((f) => f.id))

    // Add any features dynamically found in backend prompts/rubrics
    for (const p of promptsList) {
      if (p.feature && !existingIds.has(p.feature)) {
        existingIds.add(p.feature)
        list.push({
          id: p.feature,
          title: p.feature.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
          description: `Configuración de plantilla y rúbrica para ${p.feature}`,
          category: 'workspace',
        })
      }
    }
    for (const r of rubricsList) {
      if (r.feature && !existingIds.has(r.feature)) {
        existingIds.add(r.feature)
        list.push({
          id: r.feature,
          title: r.feature.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
          description: `Configuración de plantilla y rúbrica para ${r.feature}`,
          category: 'workspace',
        })
      }
    }
    return list
  }, [promptsList, rubricsList])

  const filteredFeatures = useMemo(() => {
    if (!searchQuery.trim()) return allFeatures
    const q = searchQuery.toLowerCase()
    return allFeatures.filter(
      (f) =>
        f.id.toLowerCase().includes(q) ||
        f.title.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q),
    )
  }, [allFeatures, searchQuery])

  const currentMeta = allFeatures.find((f) => f.id === selectedFeature) || {
    id: selectedFeature,
    title: selectedFeature,
    description: 'Configuración personalizada',
    category: 'workspace' as const,
  }
  const currentVersion =
    activeDocType === 'prompt' ? promptData?.version || 1 : rubricData?.version || 1

  return (
    <div className="space-y-6">
      {/* Header Info Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-blue-50/90 to-indigo-50/70 border border-blue-200/80 p-5 rounded-2xl shadow-xs">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-[#002777] text-white">
              <Bot className="h-4 w-4" />
            </span>
            <h2 className="text-base font-bold text-slate-900">
              Reglas, Prompts y Rúbricas de IA
            </h2>
          </div>
          <p className="text-xs text-slate-600 max-w-2xl leading-relaxed">
            Edita y ajusta directamente los archivos de configuración <code className="font-mono text-[11px] bg-white px-1.5 py-0.5 rounded border border-blue-200 text-[#002777]">.json</code> almacenados en <strong className="text-slate-800">/local/ai/prompts</strong> y <strong className="text-slate-800">/local/ai/rubrics</strong> para afinar las restricciones del modelo.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            disabled={loading}
            onClick={() => void loadAll()}
            className="btn btn-secondary text-xs py-2 px-3 inline-flex items-center gap-1.5 bg-white shadow-xs cursor-pointer"
            title="Recargar archivos desde el servidor"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Recargar</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="card p-12 text-center text-slate-500 bg-white border border-slate-200 rounded-2xl flex flex-col items-center justify-center gap-3">
          <RefreshCw className="h-6 w-6 animate-spin text-[#002777]" />
          <span className="text-sm font-semibold">Cargando catálogo de prompts y rúbricas...</span>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-12 items-start">
          {/* LEFT COLUMN: FEATURES LIST SELECTOR */}
          <div className="lg:col-span-4 space-y-3">
            <div className="card p-4 bg-white border border-slate-200 rounded-2xl shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Funcionalidades ({filteredFeatures.length})
                </span>
                <span className="text-[10px] text-slate-400">
                  {promptsList.length} prompts / {rubricsList.length} rúbricas
                </span>
              </div>

              {/* Search filter input */}
              <div className="relative">
                <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Buscar funcionalidad..."
                  className="input-field pl-8.5 text-xs py-1.5 border border-slate-200 rounded-xl"
                />
              </div>

              {/* Features List */}
              <div className="space-y-1.5 max-h-[600px] overflow-y-auto pr-1">
                {filteredFeatures.map((f) => {
                  const isSelected = selectedFeature === f.id
                  const pItem = promptsList.find((p) => p.feature === f.id)
                  const rItem = rubricsList.find((r) => r.feature === f.id)

                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setSelectedFeature(f.id)}
                      className={[
                        'w-full text-left p-3 rounded-xl transition-all cursor-pointer border flex flex-col gap-1',
                        isSelected
                          ? 'bg-blue-50/90 border-[#002777] shadow-xs'
                          : 'bg-white hover:bg-slate-50 border-slate-200/80 text-slate-700',
                      ].join(' ')}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={[
                            'text-xs font-bold truncate',
                            isSelected ? 'text-[#002777]' : 'text-slate-900',
                          ].join(' ')}
                        >
                          {f.title}
                        </span>
                        <code className="text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 shrink-0">
                          {f.id}
                        </code>
                      </div>

                      <p className="text-[11px] text-slate-500 line-clamp-1">{f.description}</p>

                      <div className="flex items-center gap-2 pt-1 text-[10px]">
                        <span className="inline-flex items-center gap-1 text-slate-500 font-mono">
                          P: v{pItem?.version || 1}
                        </span>
                        <span className="text-slate-300">•</span>
                        <span className="inline-flex items-center gap-1 text-slate-500 font-mono">
                          R: v{rItem?.version || 1}
                        </span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: EDITOR CANVAS */}
          <div className="lg:col-span-8 space-y-4">
            <div className="card p-6 bg-white border border-slate-200 rounded-2xl shadow-xs space-y-5">
              {/* Header of Active Editor */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-slate-900">
                      {currentMeta?.title || selectedFeature}
                    </h3>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-100 text-[#002777]">
                      v{currentVersion}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Ruta física:{' '}
                    <code className="font-mono text-[#002777] bg-slate-100 px-1 rounded">
                      /local/ai/{activeDocType === 'prompt' ? 'prompts' : 'rubrics'}/{selectedFeature}.json
                    </code>
                  </p>
                </div>

                {/* Document Type Switcher: Prompt vs Rubric */}
                <div className="inline-flex p-1 rounded-xl bg-slate-100 border border-slate-200/80 self-start sm:self-auto">
                  <button
                    type="button"
                    onClick={() => handleDocTypeSwitch('prompt')}
                    className={[
                      'px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer flex items-center gap-1.5',
                      activeDocType === 'prompt'
                        ? 'bg-white text-[#002777] shadow-xs'
                        : 'text-slate-600 hover:text-slate-900',
                    ].join(' ')}
                  >
                    <FileText className="h-3.5 w-3.5" />
                    <span>Prompt (.json)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDocTypeSwitch('rubric')}
                    className={[
                      'px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer flex items-center gap-1.5',
                      activeDocType === 'rubric'
                        ? 'bg-white text-[#002777] shadow-xs'
                        : 'text-slate-600 hover:text-slate-900',
                    ].join(' ')}
                  >
                    <ListOrdered className="h-3.5 w-3.5" />
                    <span>Rúbrica (.json)</span>
                  </button>
                </div>
              </div>

              {/* Sub-header Toolbar: View Mode & Code Actions */}
              <div className="flex flex-wrap items-center justify-between gap-2.5">
                {/* Mode Selector */}
                <div className="inline-flex items-center p-0.5 rounded-lg bg-slate-100 text-xs">
                  <button
                    type="button"
                    onClick={() => handleSwitchMode('form')}
                    className={[
                      'px-3 py-1 rounded-md font-semibold transition cursor-pointer',
                      editMode === 'form'
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900',
                    ].join(' ')}
                  >
                    Formulario Guiado
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSwitchMode('json')}
                    className={[
                      'px-3 py-1 rounded-md font-semibold transition cursor-pointer flex items-center gap-1',
                      editMode === 'json'
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900',
                    ].join(' ')}
                  >
                    <FileCode className="h-3 w-3" />
                    <span>Código JSON</span>
                  </button>
                </div>

                {/* Secondary tools */}
                <div className="flex items-center gap-2">
                  {editMode === 'json' && (
                    <button
                      type="button"
                      onClick={handlePrettifyJson}
                      className="btn btn-secondary text-[11px] py-1 px-2.5 inline-flex items-center gap-1 bg-white border border-slate-200 cursor-pointer"
                      title="Formatear e indentar JSON"
                    >
                      <Sparkles className="h-3 w-3 text-amber-600" />
                      <span>Formatear</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleCopyJson}
                    className="btn btn-secondary text-[11px] py-1 px-2.5 inline-flex items-center gap-1 bg-white border border-slate-200 cursor-pointer"
                    title="Copiar JSON al portapapeles"
                  >
                    <Copy className="h-3 w-3" />
                    <span>Copiar</span>
                  </button>
                  <button
                    type="button"
                    disabled={resetting}
                    onClick={() => void handleReset()}
                    className="btn btn-secondary text-[11px] py-1 px-2.5 inline-flex items-center gap-1 text-slate-600 hover:text-red-700 bg-white border border-slate-200 cursor-pointer"
                    title="Restaurar a los valores por defecto del sistema"
                  >
                    <RotateCcw className={`h-3 w-3 ${resetting ? 'animate-spin' : ''}`} />
                    <span>Restablecer</span>
                  </button>
                </div>
              </div>

              {/* EDITOR VIEW BODY */}
              {editMode === 'form' ? (
                /* ======================== MODO FORMULARIO GUIADO ======================== */
                <div className="space-y-5 pt-1">
                  {activeDocType === 'prompt' ? (
                    /* Form for Prompt */
                    <div className="space-y-4">
                      {/* System Prompt */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-bold text-slate-800 block flex items-center justify-between">
                          <span>Instrucción del Sistema (Rol y Reglas de Comportamiento)</span>
                          <span className="text-[10px] text-slate-400 font-normal">
                            Define el rol, tono y restricciones de invención
                          </span>
                        </label>
                        <textarea
                          rows={4}
                          value={promptData?.system || ''}
                          onChange={(e) => {
                            const updated = { ...(promptData || { version: 1, feature: selectedFeature }), system: e.target.value }
                            setPromptData(updated)
                            setRawJsonText(JSON.stringify(updated, null, 2))
                          }}
                          placeholder="Ej. You are a senior QA lead reviewing PRDs and specs. Answer ONLY from context chunks..."
                          className="input-field text-xs font-mono leading-relaxed p-3 border border-slate-200 rounded-xl"
                        />
                      </div>

                      {/* Allowed Sources Selector */}
                      <div className="space-y-2 rounded-xl bg-slate-50 p-4 border border-slate-200">
                        <label className="text-xs font-bold text-slate-800 block">
                          Fuentes de Contexto Conectadas Permitidas
                        </label>
                        <p className="text-[11px] text-slate-500">
                          Selecciona de dónde puede extraer evidencia este prompt para fundamentar sus respuestas:
                        </p>
                        <div className="grid gap-2 sm:grid-cols-2 pt-1">
                          {AVAILABLE_SOURCES.map((src) => {
                            const isChecked = (promptData?.allowed_sources || []).includes(src.id)
                            return (
                              <label
                                key={src.id}
                                className={[
                                  'flex items-center gap-2.5 p-2.5 rounded-lg border text-xs font-medium cursor-pointer transition',
                                  isChecked
                                    ? 'bg-white border-[#002777] text-[#002777] font-semibold shadow-2xs'
                                    : 'bg-white/60 border-slate-200 text-slate-700 hover:bg-white',
                                ].join(' ')}
                              >
                                <input
                                  type="checkbox"
                                  checked={isChecked}
                                  onChange={() => handleToggleSource(src.id)}
                                  className="rounded text-[#002777] focus:ring-[#002777]"
                                />
                                <span>{src.label}</span>
                              </label>
                            )
                          })}
                        </div>
                      </div>

                      {/* User Template */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-bold text-slate-800">
                            Plantilla de Usuario (Estructura del Mensaje al Modelo)
                          </label>
                          <span className="text-[10px] text-slate-400">
                            Variables inyectadas: <code className="font-mono text-[#002777]">{'{{...}}'}</code>
                          </span>
                        </div>

                        {/* Variables quick insertion pills */}
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="text-[11px] text-slate-500 mr-1 flex items-center gap-1">
                            <Zap className="h-3 w-3 text-amber-500" /> Insertar variable:
                          </span>
                          {['query', 'context', 'rubric', 'chat_context'].map((v) => (
                            <button
                              key={v}
                              type="button"
                              onClick={() => insertTemplateVariable(v)}
                              className="px-2 py-0.5 rounded-md bg-blue-50 hover:bg-blue-100 text-[#002777] text-[11px] font-mono font-semibold border border-blue-200 transition cursor-pointer"
                            >
                              +{`{${v}}`}
                            </button>
                          ))}
                        </div>

                        <textarea
                          rows={7}
                          value={promptData?.user_template || ''}
                          onChange={(e) => {
                            const updated = { ...(promptData || { version: 1, feature: selectedFeature }), user_template: e.target.value }
                            setPromptData(updated)
                            setRawJsonText(JSON.stringify(updated, null, 2))
                          }}
                          placeholder="Plantilla enviada al modelo con variables como {query}, {context}, {rubric}..."
                          className="input-field text-xs font-mono leading-relaxed p-3 border border-slate-200 rounded-xl"
                        />
                      </div>
                    </div>
                  ) : (
                    /* Form for Rubric */
                    <div className="space-y-4">
                      <div className="p-3.5 rounded-xl bg-blue-50/70 border border-blue-200 text-xs text-slate-700 leading-relaxed">
                        <strong className="text-[#002777] block mb-1">¿Qué es una rúbrica en el sistema?</strong>
                        Son criterios estrictos de evaluación inyectados en la variable <code className="font-mono bg-blue-100 px-1 rounded text-[#002777]">{'{rubric}'}</code>. El modelo LLM debe cumplir cada punto antes de emitir su respuesta.
                      </div>

                      {/* Criteria list */}
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-800 block">
                          Criterios de Evaluación Obligatorios ({(rubricData?.criteria || []).length})
                        </label>

                        <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                          {(rubricData?.criteria || []).map((crit, idx) => (
                            <div
                              key={idx}
                              className="flex items-start gap-2 p-2.5 bg-slate-50 border border-slate-200 rounded-xl group hover:bg-white transition"
                            >
                              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#002777] text-[10px] font-bold text-white mt-1">
                                {idx + 1}
                              </span>
                              <textarea
                                rows={2}
                                value={crit}
                                onChange={(e) => handleUpdateCriterion(idx, e.target.value)}
                                className="flex-1 text-xs bg-transparent border-none p-1 focus:bg-white focus:ring-1 focus:ring-[#002777] rounded leading-relaxed text-slate-800 resize-none font-medium"
                              />
                              <button
                                type="button"
                                onClick={() => handleDeleteCriterion(idx)}
                                className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer shrink-0 mt-1"
                                title="Eliminar criterio"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>

                        {/* Add criterion form */}
                        <form onSubmit={handleAddCriterion} className="flex gap-2 pt-2">
                          <input
                            type="text"
                            value={newCriterion}
                            onChange={(e) => setNewCriterion(e.target.value)}
                            placeholder="Escribe un nuevo criterio estricto para el modelo..."
                            className="input-field text-xs border border-slate-200 rounded-xl"
                          />
                          <button
                            type="submit"
                            disabled={!newCriterion.trim()}
                            className="btn btn-secondary text-xs px-3.5 py-1.5 shrink-0 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                          >
                            <Plus className="h-3.5 w-3.5" />
                            <span>Agregar Criterio</span>
                          </button>
                        </form>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                /* ======================== MODO EDITOR DE CÓDIGO JSON ======================== */
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500 font-medium flex items-center gap-1.5">
                      <FileCode className="h-3.5 w-3.5 text-[#002777]" />
                      <span>Edición directa del archivo fuente JSON</span>
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      {rawJsonText.split('\n').length} líneas
                    </span>
                  </div>

                  {jsonError && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
                      <AlertTriangle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                      <div>
                        <strong className="block font-bold">Error en la sintaxis del JSON:</strong>
                        <span className="font-mono text-[11px]">{jsonError}</span>
                      </div>
                    </div>
                  )}

                  <textarea
                    rows={16}
                    value={rawJsonText}
                    onChange={(e) => handleRawJsonChange(e.target.value)}
                    className={[
                      'w-full p-4 font-mono text-xs rounded-xl border leading-relaxed resize-y focus:outline-none focus:ring-2 shadow-inner',
                      jsonError
                        ? 'border-red-300 bg-red-50/20 focus:ring-red-500 text-red-900'
                        : 'border-slate-300 bg-slate-900 text-emerald-400 focus:ring-[#002777]',
                    ].join(' ')}
                    spellCheck={false}
                  />
                </div>
              )}

              {/* ACTION FOOTER */}
              <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span>Los cambios se guardan con incremento de versión automático.</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={saving || (editMode === 'json' && Boolean(jsonError))}
                    onClick={() => void handleSave()}
                    className="btn btn-primary text-xs py-2 px-5 inline-flex items-center gap-2 shadow-sm cursor-pointer disabled:opacity-50"
                  >
                    {saving ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Save className="h-3.5 w-3.5" />
                    )}
                    <span>{saving ? 'Guardando en disco...' : 'Guardar Cambios (.json)'}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
