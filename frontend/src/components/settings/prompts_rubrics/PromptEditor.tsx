import { Zap } from 'lucide-react'
import type { AIPromptTemplate } from '../../../api/client'
import { AVAILABLE_SOURCES } from './types'

interface PromptEditorProps {
  selectedFeature: string
  promptData: AIPromptTemplate | null
  onChange: (updated: AIPromptTemplate) => void
  onInsertVariable: (varName: string) => void
}

export const PromptEditor = ({
  selectedFeature,
  promptData,
  onChange,
  onInsertVariable,
}: PromptEditorProps) => {
  const handleToggleSource = (sourceId: string) => {
    if (!promptData) return
    const current = promptData.allowed_sources || []
    const updated = current.includes(sourceId)
      ? current.filter((s) => s !== sourceId)
      : [...current, sourceId]
    onChange({ ...promptData, allowed_sources: updated })
  }

  return (
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
            const updated: AIPromptTemplate = {
              ...(promptData || { version: 1, feature: selectedFeature }),
              system: e.target.value,
            }
            onChange(updated)
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
          {AVAILABLE_SOURCES.map((src: { id: string; label: string }) => {
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
              onClick={() => onInsertVariable(v)}
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
            const updated: AIPromptTemplate = {
              ...(promptData || { version: 1, feature: selectedFeature }),
              user_template: e.target.value,
            }
            onChange(updated)
          }}
          placeholder="Plantilla enviada al modelo con variables como {query}, {context}, {rubric}..."
          className="input-field text-xs font-mono leading-relaxed p-3 border border-slate-200 rounded-xl"
        />
      </div>
    </div>
  )
}
