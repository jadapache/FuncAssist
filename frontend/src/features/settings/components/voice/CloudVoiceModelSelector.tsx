import type { AISettings, ModelCatalogItem } from '../../../../api/client'
import { ApiKeyInput } from '../writing/ApiKeyInput'

export interface CloudVoiceModelSelectorProps {
  provider: string
  model: string
  setModel: (m: string) => void
  catalogModels: ModelCatalogItem[]
  ai: AISettings | null
  transcriptionGroqKey: string
  setTranscriptionGroqKey: (k: string) => void
  transcriptionOpenaiKey: string
  setTranscriptionOpenaiKey: (k: string) => void
  showTranscriptionKey: boolean
  setShowTranscriptionKey: (show: boolean) => void
}

export const CloudVoiceModelSelector = ({
  provider,
  model,
  setModel,
  catalogModels,
  ai,
  transcriptionGroqKey,
  setTranscriptionGroqKey,
  transcriptionOpenaiKey,
  setTranscriptionOpenaiKey,
  showTranscriptionKey,
  setShowTranscriptionKey,
}: CloudVoiceModelSelectorProps) => {
  const cloudModelsForProvider = catalogModels.filter(
    (cm) => cm.provider === provider && cm.task_type === 'transcription',
  )

  const isGroqKeyConfigured = Boolean(ai?.transcription_groq_api_key_set || ai?.groq_api_key_set)
  const isOpenaiKeyConfigured = Boolean(ai?.transcription_openai_api_key_set || ai?.openai_api_key_set)

  return (
    <div className="space-y-4 pt-1">
      {provider === 'groq' && (
        <ApiKeyInput
          label="Clave API"
          value={transcriptionGroqKey}
          onChange={setTranscriptionGroqKey}
          showKey={showTranscriptionKey}
          setShowKey={setShowTranscriptionKey}
          hasSavedKey={isGroqKeyConfigured}
          placeholder="gsk_..."
        />
      )}

      {provider === 'openai' && (
        <ApiKeyInput
          label="Clave API"
          value={transcriptionOpenaiKey}
          onChange={setTranscriptionOpenaiKey}
          showKey={showTranscriptionKey}
          setShowKey={setShowTranscriptionKey}
          hasSavedKey={isOpenaiKeyConfigured}
          placeholder="sk-..."
        />
      )}

      {/* Lista de Modelos de Transcripción Cloud con diseño idéntico a los modelos Built-in */}
      <div className="space-y-3 pt-2">
        {cloudModelsForProvider.map((cm) => {
          const isSelected =
            model === cm.id ||
            model === cm.raw_id ||
            (cm.raw_id && model.endsWith(cm.raw_id)) ||
            (cm.id && model.endsWith(cm.id))

          return (
            <div
              key={cm.id}
              onClick={() => {
                setModel(cm.raw_id || cm.id)
              }}
              className={[
                'flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl transition-all cursor-pointer select-none',
                isSelected
                  ? 'border-2 border-[#002777] bg-blue-50/20 shadow-xs'
                  : 'border border-slate-200 bg-white hover:border-slate-300',
              ].join(' ')}
            >
              <div className="space-y-1.5 flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h5 className="font-bold text-slate-900 text-base">{cm.name}</h5>
                  {isSelected && (
                    <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
                      Seleccionado
                    </span>
                  )}
                </div>

                {cm.description && (
                  <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
                    {cm.description}
                  </p>
                )}

                <p className="text-xs text-slate-400 font-medium pt-0.5 flex flex-wrap items-center gap-2">
                  <span>Formato: Audio (hasta 25MB)</span>
                  <span>•</span>
                  <span>Costo: {cm.pricing_label}</span>
                  {cm.rate_limits && (
                    <>
                      <span>•</span>
                      <span>Límites: {cm.rate_limits}</span>
                    </>
                  )}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
