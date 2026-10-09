import { CheckCircle2, Download, RefreshCw, Server, XCircle } from 'lucide-react'

export interface OllamaManagerProps {
  model: string
  setModel: (m: string) => void
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
}

export const OllamaManager = ({
  model,
  setModel,
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
}: OllamaManagerProps) => {
  return (
    <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-slate-800 flex items-center gap-2">
          <Server className="h-4 w-4 text-[#002777]" />
          <span>Servidor Ollama Remoto / Custom</span>
        </label>
        <button
          type="button"
          onClick={() => setShowEndpointSection(!showEndpointSection)}
          className="text-xs text-[#002777] font-semibold hover:underline cursor-pointer"
        >
          {showEndpointSection ? 'Ocultar Configuración de URL' : 'Configurar URL de Ollama'}
        </button>
      </div>

      {showEndpointSection && (
        <div className="space-y-2 pt-1 border-t border-slate-200">
          <label className="text-[11px] font-semibold text-slate-700 block">
            Endpoint URL de Ollama API
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="input-field text-xs font-mono py-1.5 border border-slate-200 rounded-xl"
            />
            <button
              type="button"
              disabled={fetchingModels}
              onClick={() => void fetchOllamaModels(ollamaUrl, true)}
              className="btn btn-secondary text-xs py-1.5 px-3 shrink-0 inline-flex items-center gap-1.5 cursor-pointer"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${fetchingModels ? 'animate-spin' : ''}`} />
              <span>Verificar URL</span>
            </button>
          </div>
        </div>
      )}

      {/* Estado del servidor Ollama */}
      <div className="flex items-center justify-between text-xs pt-1">
        <span className="text-slate-600 font-medium">Estado del Servicio Ollama:</span>
        {fetchingModels ? (
          <span className="inline-flex items-center gap-1 text-slate-500 font-medium">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Verificando conexión...
          </span>
        ) : ollamaOnline === true ? (
          <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-bold text-[11px]">
            <CheckCircle2 className="h-3.5 w-3.5" /> En línea ({ollamaModels.length} modelos listos)
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full font-bold text-[11px]">
            <XCircle className="h-3.5 w-3.5" /> Desconectado / Sin respuesta
          </span>
        )}
      </div>

      {/* Selector de Modelos Instalados en Ollama */}
      {ollamaOnline && ollamaModels.length > 0 && (
        <div className="space-y-1.5">
          <label className="text-xs font-bold text-slate-800 block">
            Seleccionar Modelo Instalado en Ollama
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="input-field text-xs font-mono py-2 bg-white border border-slate-200 rounded-xl w-full"
          >
            {ollamaModels.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Descarga manual de tags de Ollama */}
      <div className="pt-2 border-t border-slate-200 space-y-2">
        <label className="text-xs font-bold text-slate-800 block">
          Descargar nuevo modelo vía Ollama CLI (`ollama pull`)
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            id="custom-ollama-pull-input"
            placeholder="Ej. deepseek-r1:8b o llama3:8b"
            className="input-field text-xs font-mono py-1.5 border border-slate-200 rounded-xl"
          />
          <button
            type="button"
            disabled={isPulling}
            onClick={() => {
              const inputEl = document.getElementById(
                'custom-ollama-pull-input',
              ) as HTMLInputElement | null
              if (inputEl && inputEl.value.trim()) {
                void handlePullModel(inputEl.value.trim())
              }
            }}
            className="btn btn-secondary text-xs py-1.5 px-3 shrink-0 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            {isPulling ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            <span>Pull Tag</span>
          </button>
        </div>
      </div>

      {isPulling && pullingModelTag && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-[#002777] flex items-center gap-2">
          <RefreshCw className="h-3.5 w-3.5 animate-spin shrink-0" />
          <span className="font-mono text-[11px]">
            {pullStatusMsg || `Descargando ${pullingModelTag}...`}
          </span>
        </div>
      )}
    </div>
  )
}

