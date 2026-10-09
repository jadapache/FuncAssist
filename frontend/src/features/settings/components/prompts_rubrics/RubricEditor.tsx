import type { FormEvent } from 'react'
import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { AIRubric } from '../../../../api/client'

interface RubricEditorProps {
  rubricData: AIRubric | null
  onChange: (updated: AIRubric) => void
}

export const RubricEditor = ({ rubricData, onChange }: RubricEditorProps) => {
  const [newCriterion, setNewCriterion] = useState<string>('')

  const handleAddCriterion = (e: FormEvent) => {
    e.preventDefault()
    if (!newCriterion.trim() || !rubricData) return
    const updatedCriteria = [...(rubricData.criteria || []), newCriterion.trim()]
    onChange({ ...rubricData, criteria: updatedCriteria })
    setNewCriterion('')
  }

  const handleDeleteCriterion = (index: number) => {
    if (!rubricData) return
    const updatedCriteria = (rubricData.criteria || []).filter((_, idx) => idx !== index)
    onChange({ ...rubricData, criteria: updatedCriteria })
  }

  const handleUpdateCriterion = (index: number, val: string) => {
    if (!rubricData) return
    const updatedCriteria = [...(rubricData.criteria || [])]
    updatedCriteria[index] = val
    onChange({ ...rubricData, criteria: updatedCriteria })
  }

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-xl bg-blue-50/70 border border-blue-200 text-xs text-slate-700 leading-relaxed">
        <strong className="text-[#002777] block mb-1">¿Qué es una rúbrica en el sistema?</strong>
        Son criterios estrictos de evaluación inyectados en la variable{' '}
        <code className="font-mono bg-blue-100 px-1 rounded text-[#002777]">{'{rubric}'}</code>. El
        modelo LLM debe cumplir cada punto antes de emitir su respuesta.
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
  )
}

