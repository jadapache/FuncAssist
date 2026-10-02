import type { AISettings, ModelCatalogItem } from '../../../api/client'
import { ApiKeyInput } from './ApiKeyInput'

export interface CloudModelSelectorProps {
  provider: string
  model: string
  setModel: (m: string) => void
  catalogModels: ModelCatalogItem[]
  ai: AISettings | null
  groqKey: string
  setGroqKey: (k: string) => void
  geminiKey: string
  setGeminiKey: (k: string) => void
  openaiKey: string
  setOpenaiKey: (k: string) => void
  claudeKey: string
  setClaudeKey: (k: string) => void
  showKey: boolean
  setShowKey: (show: boolean) => void
}

export const CloudModelSelector = ({
  provider,
  model,
  setModel,
  catalogModels,
  ai,
  groqKey,
  setGroqKey,
  geminiKey,
  setGeminiKey,
  openaiKey,
  setOpenaiKey,
  claudeKey,
  setClaudeKey,
  showKey,
  setShowKey,
}: CloudModelSelectorProps) => {
  const cloudModelsForProvider = catalogModels.filter(
    (cm) => cm.provider === provider && cm.task_type === 'chat_writing',
  )

  return (
    <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
      <div className="space-y-2">
        <label className="text-xs font-bold text-slate-800 block">
          Modelo de la Nube ({provider.toUpperCase()})
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
          label="Clave API de Groq Cloud (GROQ_API_KEY)"
          value={groqKey}
          onChange={setGroqKey}
          showKey={showKey}
          setShowKey={setShowKey}
          hasSavedKey={Boolean(ai?.groq_api_key_set)}
          placeholder="gsk_..."
        />
      )}

      {provider === 'gemini' && (
        <ApiKeyInput
          label="Clave API de Google Gemini (GEMINI_API_KEY)"
          value={geminiKey}
          onChange={setGeminiKey}
          showKey={showKey}
          setShowKey={setShowKey}
          hasSavedKey={Boolean(ai?.gemini_api_key_set)}
          placeholder="AIzaSy..."
        />
      )}

      {provider === 'openai' && (
        <ApiKeyInput
          label="Clave API de OpenAI (OPENAI_API_KEY)"
          value={openaiKey}
          onChange={setOpenaiKey}
          showKey={showKey}
          setShowKey={setShowKey}
          hasSavedKey={Boolean(ai?.openai_api_key_set)}
          placeholder="sk-..."
        />
      )}

      {provider === 'claude' && (
        <ApiKeyInput
          label="Clave API de Anthropic Claude (ANTHROPIC_API_KEY)"
          value={claudeKey}
          onChange={setClaudeKey}
          showKey={showKey}
          setShowKey={setShowKey}
          hasSavedKey={Boolean(ai?.claude_api_key_set)}
          placeholder="sk-ant-..."
        />
      )}
    </div>
  )
}
