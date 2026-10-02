import React, { useState, useEffect } from 'react'
import {
  X,
  Users,
  FileText,
  CheckSquare,
  Sparkles,
  ListTodo,
  BookOpen,
  ArrowRight,
  Edit2,
  Check,
  Plus,
  Trash2,
  Loader2,
} from 'lucide-react'
import { transcriptionApi, type TranscriptionResult, type TranscriptionSummary } from '../api/transcriptionApi'
import { useToast } from '../../../context/ToastContext'

interface SummaryModalProps {
  isOpen: boolean
  transcriptionId: string | null
  onClose: () => void
  onNextGenerate: (transcriptionId: string) => void
}

export const SummaryModal: React.FC<SummaryModalProps> = ({
  isOpen,
  transcriptionId,
  onClose,
  onNextGenerate,
}) => {
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<TranscriptionResult | null>(null)
  const [summary, setSummary] = useState<TranscriptionSummary>({
    participants: [],
    topics: [],
    decisions: [],
    requirements: [],
    action_items: [],
  })
  const [saveToKb, setSaveToKb] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<'summary' | 'transcript'>('summary')
  const [editingSpeaker, setEditingSpeaker] = useState<string | null>(null)
  const [newSpeakerName, setNewSpeakerName] = useState('')

  useEffect(() => {
    if (isOpen && transcriptionId) {
      setLoading(true)
      transcriptionApi
        .getTranscriptionResult(transcriptionId)
        .then((res) => {
          setResult(res)
          if (res.summary) {
            setSummary(res.summary)
          }
        })
        .catch((err) => {
          toast.error(`Error al cargar resumen: ${err.message}`)
        })
        .finally(() => setLoading(false))
    }
  }, [isOpen, transcriptionId])

  if (!isOpen) return null

  const handleNext = async () => {
    if (!transcriptionId) return
    try {
      setIsSaving(true)
      // 1. Save any summary edits
      await transcriptionApi.updateTranscriptionSummary(transcriptionId, summary)

      // 2. Save to KB if checked and not already saved
      if (saveToKb && !result?.saved_to_knowledge) {
        await transcriptionApi.saveToKnowledgeBase(transcriptionId)
        toast.success('Minuta guardada en la Biblioteca de Conocimiento.')
      }

      onNextGenerate(transcriptionId)
    } catch (err: any) {
      toast.error(`Error al guardar: ${err.message}`)
    } finally {
      setIsSaving(false)
    }
  }

  const handleRenameSpeaker = async (oldName: string) => {
    if (!transcriptionId || !newSpeakerName.trim() || newSpeakerName === oldName) {
      setEditingSpeaker(null)
      return
    }

    try {
      const updated = await transcriptionApi.renameSpeakers(transcriptionId, { [oldName]: newSpeakerName.trim() })
      setResult(updated.transcription)
      if (updated.transcription.summary) {
        setSummary(updated.transcription.summary)
      }
      toast.success(`Interlocutor renombrado a '${newSpeakerName.trim()}'.`)
      setEditingSpeaker(null)
      setNewSpeakerName('')
    } catch (err: any) {
      toast.error(`Error al renombrar: ${err.message}`)
    }
  }

  const handleAddItem = (field: 'participants' | 'topics' | 'decisions' | 'requirements' | 'action_items') => {
    const text = prompt(`Agregar nuevo elemento a ${field}:`)
    if (text && text.trim()) {
      setSummary((prev: any) => ({
        ...prev,
        [field]: [...(prev[field] || []), text.trim()],
      }))
    }
  }

  const handleRemoveItem = (field: 'participants' | 'topics' | 'decisions' | 'requirements' | 'action_items', index: number) => {
    setSummary((prev: any) => ({
      ...prev,
      [field]: (prev[field] || []).filter((_: any, i: number) => i !== index),
    }))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-fade-in">
      <div className="card w-full max-w-3xl max-h-[90vh] bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between px-7 py-5 border-b border-slate-100 shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-[#002777] text-xs font-bold border border-blue-100">
                Resumen de Reunión
              </span>
              <span className="text-xs text-slate-400 font-mono">
                {result?.duration_seconds ? `${Math.floor(result.duration_seconds / 60)} min` : ''}
              </span>
            </div>
            <h3 className="text-lg font-bold text-slate-900 mt-1">
              {result?.metadata.title || 'Resumen y Minuta'}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex bg-slate-100 p-1 rounded-xl text-xs font-semibold">
              <button
                type="button"
                onClick={() => setActiveTab('summary')}
                className={`px-3 py-1 rounded-lg transition ${
                  activeTab === 'summary' ? 'bg-white text-[#002777] shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Resumen Ejecutivo
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('transcript')}
                className={`px-3 py-1 rounded-lg transition ${
                  activeTab === 'transcript' ? 'bg-white text-[#002777] shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Transcripción Completa
              </button>
            </div>

            <button
              type="button"
              onClick={handleNext}
              disabled={isSaving || !transcriptionId}
              className="px-3.5 py-1.5 bg-[#002777] hover:bg-[#001e5c] text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
              title="Generar Inventario y Levantamiento"
            >
              {isSaving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5 text-amber-300" />
              )}
              <span className="hidden sm:inline">Generar Documento</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition ml-1 cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-7 space-y-6 custom-scrollbar">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center space-y-3 text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
              <p className="text-xs font-medium">Cargando análisis de la reunión...</p>
            </div>
          ) : activeTab === 'summary' ? (
            <div className="space-y-6">
              {/* Participants Section */}
              <div className="card p-5 bg-slate-50/50 border border-slate-200/80 rounded-2xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wide">
                    <Users className="h-4 w-4 text-[#002777]" />
                    <span>Participantes e Interlocutores ({(summary.participants || []).length})</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleAddItem('participants')}
                    className="text-xs font-semibold text-[#002777] hover:underline flex items-center gap-1"
                  >
                    <Plus className="h-3.5 w-3.5" /> Agregar
                  </button>
                </div>

                <div className="flex flex-wrap gap-2 pt-1">
                  {(summary.participants || []).map((p, idx) => (
                    <div
                      key={idx}
                      className="group flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-xs font-medium text-slate-800 shadow-xs"
                    >
                      {editingSpeaker === p ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="text"
                            value={newSpeakerName}
                            onChange={(e) => setNewSpeakerName(e.target.value)}
                            placeholder={p}
                            className="px-2 py-0.5 text-xs border rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 w-28"
                            autoFocus
                          />
                          <button
                            type="button"
                            onClick={() => handleRenameSpeaker(p)}
                            className="text-emerald-600 hover:text-emerald-700 p-0.5"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingSpeaker(null)}
                            className="text-slate-400 hover:text-slate-600 p-0.5"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <span>{p}</span>
                          <button
                            type="button"
                            onClick={() => {
                              setEditingSpeaker(p)
                              setNewSpeakerName(p)
                            }}
                            className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-blue-600 transition"
                            title="Renombrar participante"
                          >
                            <Edit2 className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemoveItem('participants', idx)}
                            className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition ml-0.5"
                            title="Quitar"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Topics Discusssed */}
              <div className="card p-5 bg-slate-50/50 border border-slate-200/80 rounded-2xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wide">
                    <FileText className="h-4 w-4 text-blue-600" />
                    <span>Temas Clave Tratados ({(summary.topics || []).length})</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleAddItem('topics')}
                    className="text-xs font-semibold text-[#002777] hover:underline flex items-center gap-1"
                  >
                    <Plus className="h-3.5 w-3.5" /> Agregar
                  </button>
                </div>
                <div className="space-y-1.5 pt-1">
                  {(summary.topics || []).map((t, idx) => (
                    <div key={idx} className="group flex items-center justify-between gap-2 text-xs text-slate-700 bg-white p-2.5 rounded-xl border border-slate-100">
                      <span>• {t}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveItem('topics', idx)}
                        className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Decisions & Reqs Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Decisions */}
                <div className="card p-5 bg-slate-50/50 border border-slate-200/80 rounded-2xl space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wide">
                      <CheckSquare className="h-4 w-4 text-emerald-600" />
                      <span>Decisiones Acordadas</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAddItem('decisions')}
                      className="text-xs font-semibold text-emerald-700 hover:underline flex items-center gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" /> Agregar
                    </button>
                  </div>
                  <div className="space-y-1.5 pt-1">
                    {(summary.decisions || []).map((d, idx) => (
                      <div key={idx} className="group flex items-center justify-between gap-2 text-xs text-slate-700 bg-white p-2.5 rounded-xl border border-slate-100">
                        <span>✓ {d}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveItem('decisions', idx)}
                          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Requirements */}
                <div className="card p-5 bg-slate-50/50 border border-slate-200/80 rounded-2xl space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wide">
                      <Sparkles className="h-4 w-4 text-[#002777]" />
                      <span>Requerimientos Detectados</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAddItem('requirements')}
                      className="text-xs font-semibold text-[#002777] hover:underline flex items-center gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" /> Agregar
                    </button>
                  </div>
                  <div className="space-y-1.5 pt-1">
                    {(summary.requirements || []).map((r, idx) => (
                      <div key={idx} className="group flex items-center justify-between gap-2 text-xs text-slate-700 bg-white p-2.5 rounded-xl border border-slate-100">
                        <span>→ {r}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveItem('requirements', idx)}
                          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Action items */}
              {(summary.action_items || []).length > 0 && (
                <div className="card p-5 bg-slate-50/50 border border-slate-200/80 rounded-2xl space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wide">
                      <ListTodo className="h-4 w-4 text-purple-600" />
                      <span>Compromisos y Próximos Pasos</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAddItem('action_items')}
                      className="text-xs font-semibold text-purple-700 hover:underline flex items-center gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" /> Agregar
                    </button>
                  </div>
                  <div className="space-y-1.5 pt-1">
                    {(summary.action_items || []).map((act, idx) => (
                      <div key={idx} className="group flex items-center justify-between gap-2 text-xs text-slate-700 bg-white p-2.5 rounded-xl border border-slate-100">
                        <span>• {act}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveItem('action_items', idx)}
                          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Save to Knowledge Base Checkbox */}
              <label className="card p-4.5 bg-blue-50/70 border border-blue-200/80 rounded-2xl flex items-start gap-3.5 cursor-pointer hover:bg-blue-50 transition">
                <input
                  type="checkbox"
                  checked={saveToKb}
                  onChange={(e) => setSaveToKb(e.target.checked)}
                  className="h-4.5 w-4.5 mt-0.5 text-[#002777] rounded focus:ring-blue-500 cursor-pointer"
                />
                <div>
                  <p className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                    <BookOpen className="h-3.5 w-3.5 text-[#002777]" />
                    <span>Guardar transcripción y minuta en Biblioteca de Conocimiento</span>
                  </p>
                  <p className="text-[11px] text-slate-600 mt-0.5 leading-relaxed">
                    Permitirá que el Asistente Agentic RAG use esta reunión como contexto para generar automáticamente matrices QA, Historias de Usuario e Inventarios.
                  </p>
                </div>
              </label>
            </div>
          ) : (
            /* Full Transcript View */
            <div className="space-y-3">
              {result?.segments.map((seg, idx) => {
                const mins = Math.floor(seg.start / 60)
                const secs = Math.floor(seg.start % 60)
                const timeLabel = `[${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}]`

                return (
                  <div key={idx} className="p-3.5 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-[#002777]">{seg.speaker}</span>
                      <span className="font-mono text-[11px] text-slate-400">{timeLabel}</span>
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed">{seg.text}</p>
                  </div>
                )
              })}
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

          <button
            type="button"
            onClick={handleNext}
            disabled={isSaving}
            className="btn-primary px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 text-xs shadow-md shadow-blue-900/10"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Guardando...</span>
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                <span>Generar Documentos Funcionales</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
