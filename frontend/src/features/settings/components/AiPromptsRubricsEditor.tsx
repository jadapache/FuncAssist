import { useCallback, useEffect, useMemo, useState } from 'react'
import {
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
  Sparkles,
  X,
} from 'lucide-react'
import { api, type AIPromptTemplate, type AIRubric } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'
import { FEATURE_METAS, AVAILABLE_SOURCES, type FeatureMeta } from './prompts_rubrics/types'
import { FeatureSelectorSidebar } from './prompts_rubrics/FeatureSelectorSidebar'
import { PromptEditor } from './prompts_rubrics/PromptEditor'
import { RubricEditor } from './prompts_rubrics/RubricEditor'
import { JsonCodeEditor } from './prompts_rubrics/JsonCodeEditor'


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

  // Create new prompt modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newFeatureSlug, setNewFeatureSlug] = useState('')
  const [newFeatureTitle, setNewFeatureTitle] = useState('')
  const [newFeatureDesc, setNewFeatureDesc] = useState('')
  const [newFeatureSystem, setNewFeatureSystem] = useState('')
  const [newFeatureUserTemplate, setNewFeatureUserTemplate] = useState('')
  const [newFeatureSources, setNewFeatureSources] = useState<string[]>(['knowledge'])
  const [creatingPrompt, setCreatingPrompt] = useState(false)

  // Current working prompt / rubric state
  const [promptData, setPromptData] = useState<AIPromptTemplate | null>(null)
  const [rubricData, setRubricData] = useState<AIRubric | null>(null)

  // Raw JSON state for the code editor
  const [rawJsonText, setRawJsonText] = useState<string>('')
  const [jsonError, setJsonError] = useState<string | null>(null)

  // Search filter for features list
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Fetch all prompts and rubrics from backend - solo al montar o recargar explícitamente
  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [promptsRes, rubricsRes] = await Promise.all([
        api.getAiPrompts(),
        api.getAiRubrics(),
      ])
      const pList = promptsRes?.prompts || []
      const rList = rubricsRes?.rubrics || []

      setPromptsList(pList)
      setRubricsList(rList)

      // Inicializar de inmediato los datos del feature activo sin esperar un ciclo extra
      const curP = pList.find((p) => p.feature === selectedFeature) || null
      const curR = rList.find((r) => r.feature === selectedFeature) || null
      setPromptData(curP ? { ...curP } : null)
      setRubricData(curR ? { ...curR, criteria: [...(curR.criteria || [])] } : null)

      const targetObj = activeDocType === 'prompt' ? curP : curR
      if (targetObj) {
        setRawJsonText(JSON.stringify(targetObj, null, 2))
        setJsonError(null)
      }
    } catch (err) {
      console.error('Failed to load prompts/rubrics:', err)
      toast.error(err instanceof Error ? err.message : 'Error al cargar reglas y prompts')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  // Sync current selection when user picks a different feature or switches docType
  useEffect(() => {
    const curP = promptsList.find((p) => p.feature === selectedFeature) || null
    const curR = rubricsList.find((r) => r.feature === selectedFeature) || null

    setPromptData(curP ? { ...curP } : null)
    setRubricData(curR ? { ...curR, criteria: [...(curR.criteria || [])] } : null)

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
    } catch {
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
        toast.success(`Prompt para "${selectedFeature}" guardado (Versión v${saved.version})`)
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
        toast.success(`Rúbrica para "${selectedFeature}" guardada (Versión v${saved.version})`)
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
        toast.success(`Prompt para "${selectedFeature}" restablecido a valores predeterminados`)
      } else {
        const resetRes = await api.resetAiRubric(selectedFeature)
        setRubricData(resetRes)
        setRubricsList((prev) => prev.map((r) => (r.feature === selectedFeature ? resetRes : r)))
        setRawJsonText(JSON.stringify(resetRes, null, 2))
        toast.success(`Rúbrica para "${selectedFeature}" restablecida a valores predeterminados`)
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

  const handleToggleCreateSource = (srcId: string) => {
    setNewFeatureSources((prev) =>
      prev.includes(srcId) ? prev.filter((s) => s !== srcId) : [...prev, srcId],
    )
  }

  const handleCreatePromptSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const cleanSlug = newFeatureSlug
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, '_')
      .replace(/^_+|_+$/g, '')
    if (!cleanSlug) {
      toast.error('El identificador (slug) es obligatorio y debe ser alfanumérico')
      return
    }
    setCreatingPrompt(true)
    try {
      await api.createAiPrompt({
        feature: cleanSlug,
        title: newFeatureTitle.trim() || cleanSlug,
        description: newFeatureDesc.trim() || `Prompt personalizado para ${cleanSlug}`,
        system: newFeatureSystem.trim() || 'Eres un asistente especializado en QA.',
        user_template: newFeatureUserTemplate.trim() || 'Solicitud: {query}\n\nContexto:\n{context}',
        allowed_sources: newFeatureSources,
      })
      toast.success(`Prompt "${cleanSlug}" creado exitosamente`)
      setShowCreateModal(false)
      setNewFeatureSlug('')
      setNewFeatureTitle('')
      setNewFeatureDesc('')
      setNewFeatureSystem('')
      setNewFeatureUserTemplate('')
      setNewFeatureSources(['knowledge'])
      await loadAll()
      setSelectedFeature(cleanSlug)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al crear el prompt')
    } finally {
      setCreatingPrompt(false)
    }
  }

  const allFeatures = useMemo(() => {
    const list: FeatureMeta[] = [...FEATURE_METAS]
    const existingIds = new Set(list.map((f) => f.id))

    for (const p of promptsList) {
      if (p.feature && !existingIds.has(p.feature)) {
        existingIds.add(p.feature)
        list.push({
          id: p.feature,
          title: (p.title as string) || p.feature.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
          description: (p.description as string) || `Prompt personalizado para ${p.feature}`,
          category: 'custom',
          isCustom: true,
        })
      }
    }
    for (const r of rubricsList) {
      if (r.feature && !existingIds.has(r.feature)) {
        existingIds.add(r.feature)
        list.push({
          id: r.feature,
          title: (r.title as string) || r.feature.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
          description: (r.description as string) || `Configuración de rúbrica para ${r.feature}`,
          category: 'custom',
          isCustom: true,
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
        <div className="flex items-center gap-2">
          <span className="p-1.5 rounded-lg bg-[#002777] text-white">
            <Bot className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-slate-900">
            Reglas, Prompts y Rúbricas de IA
          </h2>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="btn btn-primary text-xs py-2 px-3 inline-flex items-center gap-1.5 bg-[#002777] text-white shadow-xs cursor-pointer"
            title="Crear un nuevo prompt o comando de IA"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Nuevo Prompt</span>
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => void loadAll()}
            className="btn btn-secondary text-xs py-2 px-3 inline-flex items-center gap-1.5 bg-white shadow-xs cursor-pointer"
            title="Recargar desde la base de datos"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Recargar</span>
          </button>
        </div>
      </div>

      {/* MAIN CONTENT GRID */}
      <div className="grid gap-6 lg:grid-cols-12 items-start">
        {/* LEFT COLUMN: FEATURES LIST SELECTOR */}
        <div className="lg:col-span-4 space-y-3">
          <FeatureSelectorSidebar
            features={filteredFeatures}
            selectedFeature={selectedFeature}
            promptsList={promptsList}
            rubricsList={rubricsList}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onSelectFeature={setSelectedFeature}
          />
        </div>

          {/* RIGHT COLUMN: EDITOR CANVAS */}
          <div className="lg:col-span-8 space-y-4">
            <div className="card p-6 bg-white border border-slate-200 rounded-2xl shadow-xs space-y-5">
              {/* Header of Active Editor */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">
                    {currentMeta?.title || selectedFeature}
                  </h3>
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-100 text-[#002777]">
                    v{currentVersion}
                  </span>
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
                    <span>Prompt</span>
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
                    <span>Rúbrica</span>
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
                <div className="space-y-5 pt-1">
                  {activeDocType === 'prompt' ? (
                    <PromptEditor
                      selectedFeature={selectedFeature}
                      promptData={promptData}
                      onChange={(updated: AIPromptTemplate) => {
                        setPromptData(updated)
                        setRawJsonText(JSON.stringify(updated, null, 2))
                      }}
                      onInsertVariable={insertTemplateVariable}
                    />
                  ) : (
                    <RubricEditor
                      rubricData={rubricData}
                      onChange={(updated: AIRubric) => {
                        setRubricData(updated)
                        setRawJsonText(JSON.stringify(updated, null, 2))
                      }}
                    />
                  )}
                </div>
              ) : (
                <JsonCodeEditor
                  rawJsonText={rawJsonText}
                  jsonError={jsonError}
                  onChange={handleRawJsonChange}
                />
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
                    <span>{saving ? 'Guardando...' : 'Guardar Cambios'}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

      {/* Create Prompt Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto font-sans">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="p-1 rounded-lg bg-[#002777] text-white">
                  <Plus className="h-4 w-4" />
                </span>
                <h3 className="text-base font-bold text-slate-900">Crear Nuevo Prompt de IA</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreatePromptSubmit} className="space-y-4 text-xs">
              <div className="space-y-1">
                <label className="font-bold text-slate-800 block">
                  Identificador Único (Comando / Slug)
                </label>
                <input
                  type="text"
                  value={newFeatureSlug}
                  onChange={(e) => setNewFeatureSlug(e.target.value)}
                  placeholder="ej: qa_security o auditoria"
                  className="input-field text-xs text-slate-800 w-full font-mono"
                  required
                />
                <span className="text-[10px] text-slate-400">
                  Se utilizará como comando de acceso directo en el chat (ej: /{newFeatureSlug.toLowerCase().trim() || 'slug'})
                </span>
              </div>

              <div className="space-y-1">
                <label className="font-bold text-slate-800 block">
                  Título Descriptivo
                </label>
                <input
                  type="text"
                  value={newFeatureTitle}
                  onChange={(e) => setNewFeatureTitle(e.target.value)}
                  placeholder="ej: Auditoría de Seguridad y Vulnerabilidades"
                  className="input-field text-xs text-slate-800 w-full"
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="font-bold text-slate-800 block">
                  Descripción Corta
                </label>
                <input
                  type="text"
                  value={newFeatureDesc}
                  onChange={(e) => setNewFeatureDesc(e.target.value)}
                  placeholder="ej: Evalúa especificaciones funcionales detectando riesgos de seguridad..."
                  className="input-field text-xs text-slate-800 w-full"
                />
              </div>

              <div className="space-y-1">
                <label className="font-bold text-slate-800 block">
                  Instrucción del Sistema (Rol y Reglas)
                </label>
                <textarea
                  rows={3}
                  value={newFeatureSystem}
                  onChange={(e) => setNewFeatureSystem(e.target.value)}
                  placeholder="Eres un especialista en seguridad QA..."
                  className="input-field text-xs text-slate-800 w-full font-mono p-2.5"
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="font-bold text-slate-800 block">
                  Plantilla de Mensaje de Usuario
                </label>
                <textarea
                  rows={2}
                  value={newFeatureUserTemplate}
                  onChange={(e) => setNewFeatureUserTemplate(e.target.value)}
                  placeholder="Solicitud: {query}\n\nContexto:\n{context}"
                  className="input-field text-xs text-slate-800 w-full font-mono p-2.5"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-bold text-slate-800 block">
                  Fuentes de Contexto Conectadas
                </label>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  {AVAILABLE_SOURCES.map((src) => (
                    <label
                      key={src.id}
                      className="flex items-center gap-2 p-2 rounded-lg border border-slate-200 bg-slate-50 cursor-pointer text-[11px]"
                    >
                      <input
                        type="checkbox"
                        checked={newFeatureSources.includes(src.id)}
                        onChange={() => handleToggleCreateSource(src.id)}
                        className="rounded text-[#002777]"
                      />
                      <span className="truncate">{src.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn btn-secondary text-xs py-2 px-4 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={creatingPrompt}
                  className="btn btn-primary text-xs py-2 px-5 bg-[#002777] text-white cursor-pointer disabled:opacity-50"
                >
                  {creatingPrompt ? 'Guardando...' : 'Crear y Activar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
