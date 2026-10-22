import { useEffect, useState, useCallback } from 'react'
import {
  Cpu,
  Download,
  HardDrive,
  Loader2,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react'
import { webLLMProvider } from '../../../ai/providers/WebLLMProvider'
import {
  WEBLLM_MODELS_CATALOG,
  detectHardwareProfile,
  evaluateModel,
} from '../../../ai/policies/modelSelectionPolicy'
import type {
  HardwareProfile,
  WebLLMInitProgress,
  WebLLMModelDefinition,
} from '../../../ai/types/webLlm'

export interface BuiltinModelsListProps {
  model: string
  setModel: (m: string) => void
}

export const BuiltinModelsList = ({
  model,
  setModel,
}: BuiltinModelsListProps) => {
  const [cachedMap, setCachedMap] = useState<Record<string, boolean>>({})
  const [hardware, setHardware] = useState<HardwareProfile | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [progressState, setProgressState] = useState<Record<string, WebLLMInitProgress>>({})
  const [isRefreshing, setIsRefreshing] = useState(false)

  const refreshCacheStatus = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const nextMap: Record<string, boolean> = {}
      for (const m of WEBLLM_MODELS_CATALOG) {
        nextMap[m.id] = await webLLMProvider.isModelCached(m.id)
      }
      setCachedMap(nextMap)
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    let isMounted = true
    const init = async () => {
      const profile = await detectHardwareProfile()
      if (isMounted) {
        setHardware(profile)
      }
      await refreshCacheStatus()
    }
    void init()
    return () => {
      isMounted = false
    }
  }, [refreshCacheStatus])

  const handleDownload = async (modelDef: WebLLMModelDefinition) => {
    setDownloadingId(modelDef.id)
    setProgressState((prev) => ({
      ...prev,
      [modelDef.id]: { progress: 0, text: 'Iniciando conexión con Hugging Face...', timeElapsed: 0 },
    }))

    try {
      await webLLMProvider.initModel(modelDef.id, (report) => {
        setProgressState((prev) => ({
          ...prev,
          [modelDef.id]: report,
        }))
      })
      await refreshCacheStatus()
      setModel(modelDef.id)
    } catch (err) {
      console.error(`Error inicializando modelo ${modelDef.id}:`, err)
    } finally {
      setDownloadingId(null)
    }
  }

  const handleDelete = async (modelId: string) => {
    setDeletingId(modelId)
    try {
      await webLLMProvider.deleteCachedModel(modelId)
      await refreshCacheStatus()
    } catch (err) {
      console.error(`Error eliminando modelo ${modelId}:`, err)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[#002777]" />
            <span>Modelos de IA Integrados (Navegador WebGPU)</span>
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            Modelos de lenguaje ejecutados íntegramente en tu navegador mediante WebLLM y WebGPU. Cero consumo en el servidor y total privacidad de datos.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void refreshCacheStatus()}
          disabled={isRefreshing}
          title="Actualizar estado de caché en navegador"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={['h-3.5 w-3.5', isRefreshing ? 'animate-spin' : ''].join(' ')} />
          <span>Actualizar</span>
        </button>
      </div>

      {hardware && !hardware.hasWebGPU && (
        <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-2.5 text-xs text-amber-800">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block">Aceleración WebGPU no detectada</span>
            <span>
              Tu navegador o hardware no tiene WebGPU habilitado. Se recomienda utilizar Google Chrome o Microsoft Edge actualizado para ejecutar modelos en el navegador.
            </span>
          </div>
        </div>
      )}

      {hardware && hardware.hasWebGPU && (
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs text-slate-700">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-[#002777]" />
            <span>Dispositivo detectado: <strong className="font-semibold text-slate-900">{hardware.adapterName}</strong></span>
          </div>
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3 text-emerald-600" />
            WebGPU Activo ({hardware.hasShaderF16 ? 'shader-f16 compatible' : 'shader estándar'})
          </span>
        </div>
      )}

      <div className="space-y-3">
        {WEBLLM_MODELS_CATALOG.map((m) => {
          const isDownloaded = Boolean(cachedMap[m.id])
          const isSelected = model === m.id
          const isDownloading = downloadingId === m.id
          const isDeleting = deletingId === m.id
          const progressInfo = progressState[m.id]
          const evaluation = hardware ? evaluateModel(m, hardware, 'balanced') : null

          return (
            <div
              key={m.id}
              onClick={() => {
                setModel(m.id)
              }}
              className={[
                'flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl transition-all cursor-pointer',
                isSelected
                  ? 'border-2 border-[#002777] bg-blue-50/20 shadow-xs'
                  : 'border border-slate-200 bg-white hover:border-slate-300',
              ].join(' ')}
            >
              <div className="space-y-1.5 flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h5 className="font-bold text-slate-900 text-base">{m.name}</h5>
                  {isDownloaded ? (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      En caché del navegador
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200">
                      No descargado ({m.downloadSize})
                    </span>
                  )}
                  {isSelected && (
                    <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
                      Seleccionado
                    </span>
                  )}
                  {evaluation?.isRecommended && (
                    <span className="rounded-md bg-purple-50 px-2 py-0.5 text-xs font-semibold text-purple-700 border border-purple-200">
                      Recomendado para tu equipo
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
                  {m.description}
                </p>

                <p className="text-xs text-slate-400 font-medium pt-0.5 flex flex-wrap items-center gap-2">
                  <span>Descarga: {m.downloadSize}</span>
                  <span>•</span>
                  <span>VRAM requerida: {m.vramFormatted}</span>
                  <span>•</span>
                  <span>Ventana de Contexto: {m.contextWindow}</span>
                </p>

                {isDownloading && progressInfo && (
                  <div className="pt-2 space-y-1.5">
                    <div className="flex justify-between text-xs font-semibold text-slate-700">
                      <span>{progressInfo.text || 'Descargando y compilando pesos...'}</span>
                      <span>{progressInfo.progress}%</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-[#002777] h-2 rounded-full transition-all duration-300"
                        style={{ width: `${progressInfo.progress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                {isDownloaded ? (
                  <>
                    <button
                      type="button"
                      disabled={isDeleting || isDownloading}
                      onClick={() => void handleDelete(m.id)}
                      title="Eliminar modelo de la caché del navegador"
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition cursor-pointer disabled:opacity-50"
                    >
                      {isDeleting ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                      Liberar caché
                    </button>

                    <button
                      type="button"
                      onClick={() => setModel(m.id)}
                      className={[
                        'px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer',
                        isSelected
                          ? 'bg-[#002777] text-white font-bold'
                          : 'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700',
                      ].join(' ')}
                    >
                      {isSelected ? 'Activo' : 'Seleccionar'}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={isDownloading}
                    onClick={() => void handleDownload(m)}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-blue-50 text-[#002777] hover:bg-blue-100 border border-blue-200 transition cursor-pointer disabled:opacity-50"
                  >
                    {isDownloading ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Descargando...</span>
                      </>
                    ) : (
                      <>
                        <Download className="h-3.5 w-3.5" />
                        <span>Descargar ({m.downloadSize})</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
