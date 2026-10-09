import type { AISettings, ModelCatalogItem } from '../../../api/client'
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
    <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
      <div className="space-y-2">
        <label className="text-xs font-bold text-slate-800 block">
          Modelo de Transcripción Cloud ({provider.toUpperCase()})
        </label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="input-field text-xs py-2 bg-white border border-slate-200 rounded-xl w-full"
        >
          {cloudModelsForProvider.length > 0 ? (
            cloudModelsForProvider.map((cm) => (
              <option key={cm.id} value={cm.raw_id || cm.id}>
                {cm.name} ({cm.raw_id || cm.id})
              </option>
            ))
          ) : (
            <option value={model}>{model}</option>
          )}
        </select>
      </div>

      {provider === 'groq' && (
        <ApiKeyInput
          label="Clave API de Groq Cloud para Transcripción (Opcional si ya se configuró en Redacción)"
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
          label="Clave API de OpenAI para Transcripción (Opcional si ya se configuró en Redacción)"
          value={transcriptionOpenaiKey}
          onChange={setTranscriptionOpenaiKey}
          showKey={showTranscriptionKey}
          setShowKey={setShowTranscriptionKey}
          hasSavedKey={isOpenaiKeyConfigured}
          placeholder="sk-..."
        />
      )}
    </div>
  )
}
