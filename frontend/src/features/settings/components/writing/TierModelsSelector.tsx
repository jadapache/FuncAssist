import type { ModelCatalogItem } from '../../../../api/client'

export const MAX_FALLBACK_MODELS = 3

export interface TierModelsSelectorProps {
  provider: string
  mainModel: string
  catalogModels: ModelCatalogItem[]
  fastModel: string
  setFastModel: (m: string) => void
  fallbackModels: string[]
  setFallbackModels: (models: string[]) => void
}

const modelId = (m: ModelCatalogItem) => m.raw_id || m.id

/**
 * Fast model (auxiliary calls: planning, summaries, map-reduce) and up to three fallback models,
 * chosen from the active provider's catalog so only existing models can be saved.
 */
export const TierModelsSelector = ({
  provider,
  mainModel,
  catalogModels,
  fastModel,
  setFastModel,
  fallbackModels,
  setFallbackModels,
}: TierModelsSelectorProps) => {
  const options = catalogModels
    .filter((m) => m.provider === provider && m.task_type === 'chat_writing')
    .map(modelId)
    .filter((id, idx, all) => all.indexOf(id) === idx)
    .sort((a, b) => a.localeCompare(b))

  if (options.length === 0) return null

  const fallbackSlots = Array.from({ length: MAX_FALLBACK_MODELS }, (_, i) => fallbackModels[i] ?? '')

  const updateFallback = (slot: number, value: string) => {
    const next = [...fallbackSlots]
    next[slot] = value
    setFallbackModels(next.filter((m, i) => m && next.indexOf(m) === i))
  }

  const selectClass =
    'input-field text-sm text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2 px-3'

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-slate-50/50 p-4">
      <div className="space-y-1.5">
        <label className="text-xs font-semibold text-slate-800 block" htmlFor="fast-model-select">
          Modelo rápido
        </label>
        <p className="text-[11px] text-slate-500">
          Se usa para planificar documentos, resumir el historial y condensar documentos extensos.
        </p>
        <select
          id="fast-model-select"
          value={fastModel}
          onChange={(e) => setFastModel(e.target.value)}
          className={selectClass}
        >
          <option value="">Automático (elegido del catálogo)</option>
          {options.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <span className="text-xs font-semibold text-slate-800 block">Modelos de respaldo</span>
        <p className="text-[11px] text-slate-500">
          Se prueban en orden si el modelo principal falla (por ejemplo, por límite de cuota).
        </p>
        <div className="grid gap-2 sm:grid-cols-3">
          {fallbackSlots.map((value, slot) => {
            const takenElsewhere = new Set(fallbackSlots.filter((m, i) => m && i !== slot))
            const disabled = slot > 0 && !fallbackSlots[slot - 1]
            return (
              <select
                key={slot}
                aria-label={`Modelo de respaldo ${slot + 1}`}
                value={value}
                disabled={disabled}
                onChange={(e) => updateFallback(slot, e.target.value)}
                className={`${selectClass} disabled:opacity-50`}
              >
                <option value="">{`Respaldo ${slot + 1}: ninguno`}</option>
                {options
                  .filter((id) => id !== mainModel && !takenElsewhere.has(id))
                  .map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
              </select>
            )
          })}
        </div>
      </div>
    </div>
  )
}
