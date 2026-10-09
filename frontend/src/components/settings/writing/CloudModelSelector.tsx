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
    <div className="space-y-4 pt-1">
      {provider === 'groq' && (
        <ApiKeyInput
          label="Clave API"
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
          label="Clave API"
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
          label="Clave API"
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
          label="Clave API"
          value={claudeKey}
          onChange={setClaudeKey}
          showKey={showKey}
          setShowKey={setShowKey}
          hasSavedKey={Boolean(ai?.claude_api_key_set)}
          placeholder="sk-ant-..."
        />
      )}

      {/* Lista de Modelos Cloud con diseño idéntico al de modelos Built-in */}
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
                  <span>Ventana de Contexto: {cm.context_window}</span>
                  {cm.max_output_tokens && (
                    <>
                      <span>•</span>
                      <span>Salida máx: {cm.max_output_tokens.toLocaleString()} tokens</span>
                    </>
                  )}
                  <span>•</span>
                  <span>Precios: {cm.pricing_label}</span>
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
