import { CheckCircle2, RefreshCw, Server, XCircle } from 'lucide-react'
import { validateRemoteEndpointUrl } from '../../validators/settingsValidation'

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
}: OllamaManagerProps) => {
  const urlValidation = ollamaUrl.trim()
    ? validateRemoteEndpointUrl(ollamaUrl, false)
    : { isValid: true }

  return (
    <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-slate-800 flex items-center gap-2">
          <Server className="h-4 w-4 text-[#002777]" />
          <span>Servidor Ollama Remoto (HTTPS Externo)</span>
        </label>
        <button
          type="button"
          onClick={() => setShowEndpointSection(!showEndpointSection)}
          className="text-xs text-[#002777] font-semibold hover:underline cursor-pointer"
        >
          {showEndpointSection ? 'Ocultar Configuración de URL' : 'Configurar URL de Ollama Remoto'}
        </button>
      </div>

      <p className="text-xs text-slate-500">
        Conéctate a una instancia remota de Ollama alojada fuera de esta máquina. Por seguridad y aislamiento, no se admiten conexiones a localhost ni a redes privadas.
      </p>

      {showEndpointSection && (
        <div className="space-y-2 pt-1 border-t border-slate-200">
          <label className="text-[11px] font-semibold text-slate-700 block">
            Endpoint URL de Ollama Remoto (HTTPS obligatorio)
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              placeholder="https://ollama.tu-dominio.com"
              className="input-field text-xs font-mono py-1.5 border border-slate-200 rounded-xl flex-1"
            />
            <button
              type="button"
              disabled={fetchingModels || !ollamaUrl.trim() || !urlValidation.isValid}
              onClick={() => void fetchOllamaModels(ollamaUrl, true)}
              className="btn btn-secondary text-xs py-1.5 px-3 shrink-0 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${fetchingModels ? 'animate-spin' : ''}`} />
              <span>Verificar Conexión</span>
            </button>
          </div>
          {!urlValidation.isValid && urlValidation.error && (
            <p className="text-[11px] text-red-600 font-medium">
              {urlValidation.error}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between text-xs pt-1">
        <span className="text-slate-600 font-medium">Estado del Servicio Remoto:</span>
        {fetchingModels ? (
          <span className="inline-flex items-center gap-1 text-slate-500 font-medium">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Verificando conexión...
          </span>
        ) : ollamaOnline === true ? (
          <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-bold text-[11px]">
            <CheckCircle2 className="h-3.5 w-3.5" /> En línea ({ollamaModels.length} modelos remotos disponibles)
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-slate-600 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full font-medium text-[11px]">
            <XCircle className="h-3.5 w-3.5 text-slate-400" /> Sin conexión
          </span>
        )}
      </div>

      {ollamaOnline && ollamaModels.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <label className="text-xs font-bold text-slate-800 block">
            Seleccionar Modelo Expuesto por el Servidor Remoto
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
    </div>
  )
}
