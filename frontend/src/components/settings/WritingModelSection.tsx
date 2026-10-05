import type { FormEvent } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  RefreshCw,
  Zap,
} from 'lucide-react'
import type { AISettings, LocalBuiltinModelInfo, ModelCatalogItem } from '../../api/client'
import { BuiltinModelsList } from './writing/BuiltinModelsList'
import { CloudModelSelector } from './writing/CloudModelSelector'
import { OllamaManager } from './writing/OllamaManager'

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
  isPulling: boolean
  pullingModelTag: string | null
  pullStatusMsg: string | null
  handlePullModel: (tag: string) => Promise<void>
  localBuiltinModels?: LocalBuiltinModelInfo[]
  downloadingBuiltinId?: string | null
  deletingBuiltinId?: string | null
  fetchingBuiltinModels?: boolean
  fetchLocalBuiltinModels?: () => Promise<void>
  handleDownloadBuiltinModel?: (modelId: string) => Promise<void>
  handleDeleteBuiltinModel?: (modelId: string) => Promise<void>
  downloadTasks?: Record<string, { progress: number; speedOrSize?: string | null; stageText?: string }>
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
  isPulling,
  pullingModelTag,
  pullStatusMsg,
  handlePullModel,
  localBuiltinModels,
  downloadingBuiltinId,
  deletingBuiltinId,
  fetchingBuiltinModels,
  fetchLocalBuiltinModels,
  handleDownloadBuiltinModel,
  handleDeleteBuiltinModel,
  downloadTasks,

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
  // Modelos built-in cargados dinámicamente desde local/ai/builtin_models_catalog.json
  const builtinModelsList = (localBuiltinModels && localBuiltinModels.length > 0)
    ? localBuiltinModels.map((lm) => ({
        id: lm.id,
        name: lm.name,
        tag: lm.id,
        description: lm.description || '',
        size: lm.size || '~1.2 GiB',
        tokens: lm.tokens || '32k tokens',
      }))
    : catalogModels
        .filter((m) => m.provider === 'builtin' && m.task_type === 'chat_writing')
        .map((cm) => ({
          id: cm.id,
          name: cm.name,
          tag: cm.raw_id || cm.id,
          description: cm.description,
          size: cm.size || '~1.2 GiB',
          tokens: cm.context_window || '32k tokens',
        }))


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
              Modelos de lenguaje optimizados para redacción de historias de usuario, criterios de aceptación Gherkin y chat interactivo.
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
          {/* Selector de Proveedor / Tipo de Modelo */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-800 block">
              Proveedor del Modelo de Inferencia
            </label>

            <select
              value={provider}
              onChange={(e) => {
                const newProv = e.target.value
                setProvider(newProv)
                if (newProv === 'builtin') {
                  setModel('qwen3.5:2b')
                } else if (newProv === 'ollama') {
                  if (ollamaModels.length > 0) {
                    setModel(ollamaModels[0])
                  } else {
                    setModel('gemma3:1b')
                  }
                  void fetchOllamaModels(undefined, false)
                } else if (newProv === 'groq') {
                  setModel('llama-3.3-70b-versatile')
                } else if (newProv === 'gemini') {
                  setModel('gemini-1.5-flash')
                } else if (newProv === 'openai') {
                  setModel('gpt-4o-mini')
                } else if (newProv === 'claude') {
                  setModel('claude-3-5-haiku-latest')
                }
              }}
              className="input-field text-sm font-medium text-slate-900 w-full bg-white border border-slate-300 rounded-xl py-2.5 px-3"
            >
              <option value="builtin">IA Integrada (Local, Sin API externa)</option>
              <option value="ollama">Ollama (Servidor Local / Remoto)</option>
              <option value="groq">Groq (API en la Nube)</option>
              <option value="gemini">Google Gemini (API en la Nube)</option>
              <option value="openai">OpenAI (API en la Nube)</option>
              <option value="claude">Claude (Anthropic API en la Nube)</option>
            </select>
          </div>

          {/* CASO 1: IA INTEGRADA LOCAL */}
          {provider === 'builtin' && (
            <BuiltinModelsList
              builtinModelsList={builtinModelsList}
              model={model}
              setModel={setModel}
              localBuiltinModels={localBuiltinModels}
              downloadingBuiltinId={downloadingBuiltinId}
              deletingBuiltinId={deletingBuiltinId}
              fetchingBuiltinModels={fetchingBuiltinModels}
              fetchLocalBuiltinModels={fetchLocalBuiltinModels}
              handleDownloadBuiltinModel={handleDownloadBuiltinModel}
              handleDeleteBuiltinModel={handleDeleteBuiltinModel}
              downloadTasks={downloadTasks}
            />
          )}

          {/* CASO 2: PROVEEDOR OLLAMA */}
          {provider === 'ollama' && (
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
              isPulling={isPulling}
              pullingModelTag={pullingModelTag}
              pullStatusMsg={pullStatusMsg}
              handlePullModel={handlePullModel}
            />
          )}

          {/* CASO 3: PROVEEDORES CLOUD (GROQ, GEMINI, OPENAI, CLAUDE) */}
          {['groq', 'gemini', 'openai', 'claude'].includes(provider) && (
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

          {/* Botones Probar Conexión y Guardar */}
          <div className="flex flex-wrap items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              disabled={testingConnection || savingAi}
              onClick={() => void handleTestConnection()}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium px-5 py-2.5 shadow-sm transition text-sm disabled:opacity-60 cursor-pointer"
            >
              {testingConnection ? <RefreshCw className="h-4 w-4 animate-spin text-blue-600" /> : <Zap className="h-4 w-4 text-amber-500" />}
              <span>{testingConnection ? 'Probando Conexión…' : 'Probar Conexión'}</span>
            </button>

            <button
              type="submit"
              disabled={savingAi || testingConnection}
              className="bg-[#002777] hover:bg-[#001f5f] text-white font-bold px-6 py-2.5 rounded-xl shadow-xs transition flex items-center gap-2 cursor-pointer text-sm disabled:opacity-50"
            >
              {savingAi ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              <span>Guardar Modelo de Redacción</span>
            </button>
          </div>
        </>
      )}
    </form>
  )
}

