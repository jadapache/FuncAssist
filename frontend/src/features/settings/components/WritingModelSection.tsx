import type { FormEvent } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  RefreshCw,
  Zap,
} from 'lucide-react'
import type { AISettings, ModelCatalogItem } from '../../../api/client'
import { BuiltinModelsList } from './writing/BuiltinModelsList'
import { CloudModelSelector } from './writing/CloudModelSelector'
import { OllamaManager } from './writing/OllamaManager'
import { DEFAULT_WEBLLM_MODEL } from '../../ai/catalogs/clientCatalog'

export type WritingModelSectionProps = {
  ai: AISettings | null
  provider: string
  setProvider: (p: string) => void
  model: string
  setModel: (m: string) => void
  isWritingOpen: boolean
  setIsWritingOpen: (open: boolean) => void
  showEndpointSection: boolean
  setShowEndpointSection: (show: boolean) => void
  ollamaUrl: string
  setOllamaUrl: (url: string) => void
  ollamaOnline: boolean | null
  ollamaModels: string[]
  fetchingModels: boolean
  fetchOllamaModels: (url?: string, isUserAction?: boolean) => Promise<void>
  catalogModels: ModelCatalogItem[]
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
  savingAi: boolean
  testingConnection: boolean
  handleAiSave: (e?: FormEvent) => Promise<void>
  handleTestConnection: () => Promise<void>
}

export const WritingModelSection = ({
  ai,
  provider,
  setProvider,
  model,
  setModel,
  isWritingOpen,
  setIsWritingOpen,
  showEndpointSection,
  setShowEndpointSection,
  ollamaUrl,
  setOllamaUrl,
  ollamaOnline,
  ollamaModels,
  fetchingModels,
  fetchOllamaModels,
  catalogModels,
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
  savingAi,
  testingConnection,
  handleAiSave,
  handleTestConnection,
}: WritingModelSectionProps) => {
  const isBrowserMode = provider === 'local' || provider === 'builtin' || provider === 'webllm'
  const isOllamaRemote = provider === 'ollama_remote' || provider === 'ollama'

  return (
    <form
      onSubmit={(e) => void handleAiSave(e)}
      className="card space-y-6 border border-slate-200 bg-white p-6 md:p-8 shadow-sm rounded-2xl transition-all"
    >
      <div
        onClick={() => setIsWritingOpen(!isWritingOpen)}
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4 cursor-pointer select-none"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-blue-100 text-blue-700">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Modelo de Redacción y Chat</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Modelos de lenguaje ejecutados en tu navegador o mediante APIs externas configuradas.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
          {!isWritingOpen && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
              Activo: <span className="font-mono text-[11px] text-[#002777] font-bold">{provider} • {model}</span>
            </span>
          )}
          <div
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
            title={isWritingOpen ? 'Plegar panel' : 'Desplegar panel'}
          >
            {isWritingOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </div>
        </div>
      </div>

      {isWritingOpen && (
        <>
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-800 block">
              Proveedor del Modelo de Inferencia
            </label>

            <select
              value={isBrowserMode ? 'local' : isOllamaRemote ? 'ollama_remote' : provider}
              onChange={(e) => {
                const newProv = e.target.value
                setProvider(newProv)
                if (newProv === 'local') {
                  setModel(DEFAULT_WEBLLM_MODEL)
                } else if (newProv === 'ollama_remote') {
                  setModel(ollamaModels.length > 0 ? ollamaModels[0] : 'qwen2.5:2b')
                  void fetchOllamaModels(undefined, false)
                } else if (newProv === 'groq') {
                  setModel('llama-3.3-70b-versatile')
                } else if (newProv === 'gemini') {
                  setModel('gemini-2.5-flash')
                } else if (newProv === 'openai') {
                  setModel('gpt-4o-mini')
                } else if (newProv === 'claude') {
                  setModel('claude-3-5-haiku-latest')
                }
              }}
              className="input-field text-sm font-medium text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2.5 px-3"
            >
              <option value="local">En este navegador (WebLLM / WebGPU)</option>
              <option value="ollama_remote">Ollama Remoto (HTTPS externo)</option>
              <option value="groq">Groq (API)</option>
              <option value="gemini">Google Gemini (API)</option>
              <option value="openai">OpenAI (API)</option>
              <option value="claude">Claude (API)</option>
            </select>
          </div>

          {isBrowserMode && (
            <BuiltinModelsList
              model={model}
              setModel={setModel}
            />
          )}

          {isOllamaRemote && (
            <OllamaManager
              model={model}
              setModel={setModel}
              showEndpointSection={showEndpointSection}
              setShowEndpointSection={setShowEndpointSection}
              ollamaUrl={ollamaUrl}
              setOllamaUrl={setOllamaUrl}
              ollamaOnline={ollamaOnline}
              ollamaModels={ollamaModels}
              fetchingModels={fetchingModels}
              fetchOllamaModels={fetchOllamaModels}
            />
          )}

          {!isBrowserMode && !isOllamaRemote && (
            <CloudModelSelector
              provider={provider}
              model={model}
              setModel={setModel}
              catalogModels={catalogModels}
              ai={ai}
              groqKey={groqKey}
              setGroqKey={setGroqKey}
              geminiKey={geminiKey}
              setGeminiKey={setGeminiKey}
              openaiKey={openaiKey}
              setOpenaiKey={setOpenaiKey}
              claudeKey={claudeKey}
              setClaudeKey={setClaudeKey}
              showKey={showKey}
              setShowKey={setShowKey}
            />
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              disabled={testingConnection || savingAi}
              onClick={() => void handleTestConnection()}
              className="btn btn-secondary text-xs px-4 py-2 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {testingConnection ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Zap className="h-3.5 w-3.5 text-amber-500" />
              )}
              <span>Probar Conexión</span>
            </button>

            <button
              type="submit"
              disabled={savingAi || testingConnection}
              className="bg-[#002777] hover:bg-[#001f5f] text-white font-bold px-6 py-2.5 rounded-xl shadow-xs transition flex items-center gap-2 cursor-pointer text-sm disabled:opacity-50"
            >
              {savingAi ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              <span>Guardar Configuración</span>
            </button>
          </div>
        </>
      )}
    </form>
  )
}
