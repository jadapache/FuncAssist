import { Download, HardDrive, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import type { LocalBuiltinModelInfo } from '../../../../api/client'

export interface BuiltinModelItem {
  id: string
  name: string
  tag?: string
  description: string
  size: string
  tokens: string
}

export interface BuiltinModelsListProps {
  builtinModelsList: BuiltinModelItem[]
  model: string
  setModel: (m: string) => void
  localBuiltinModels?: LocalBuiltinModelInfo[]
  downloadingBuiltinId?: string | null
  deletingBuiltinId?: string | null
  fetchingBuiltinModels?: boolean
  fetchLocalBuiltinModels?: () => Promise<void>
  handleDownloadBuiltinModel?: (modelId: string) => Promise<void>
  handleDeleteBuiltinModel?: (modelId: string) => Promise<void>
  downloadTasks?: Record<string, { progress: number; speedOrSize?: string | null; stageText?: string }>
}

export const BuiltinModelsList = ({
  builtinModelsList,
  model,
  setModel,
  localBuiltinModels = [],
  downloadingBuiltinId = null,
  deletingBuiltinId = null,
  fetchingBuiltinModels = false,
  fetchLocalBuiltinModels,
  handleDownloadBuiltinModel,
  handleDeleteBuiltinModel,
  downloadTasks = {},
}: BuiltinModelsListProps) => {
  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[#002777]" />
            <span>Modelos de IA Integrados (Local)</span>
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            Modelos GGUF descargados directamente a tu equipo desde repositorios oficiales. No requieren instalación de Ollama.
          </p>
        </div>

        {fetchLocalBuiltinModels && (
          <button
            type="button"
            onClick={() => void fetchLocalBuiltinModels()}
            disabled={fetchingBuiltinModels}
            title="Actualizar estado de modelos en disco"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition cursor-pointer self-start sm:self-auto disabled:opacity-50"
          >
            <RefreshCw className={['h-3.5 w-3.5', fetchingBuiltinModels ? 'animate-spin' : ''].join(' ')} />
            <span>Actualizar</span>
          </button>
        )}
      </div>

      <div className="space-y-3">
        {builtinModelsList.map((m) => {
          const localInfo = localBuiltinModels.find((lm) => lm.id === m.id || (m.tag && lm.id === m.tag))
          const isDownloaded = Boolean(localInfo?.is_downloaded)
          const isSelected = model === m.id || (m.tag ? model === m.tag : false)
          const isDownloading = Boolean(
            downloadingBuiltinId && (downloadingBuiltinId === m.id || (m.tag && downloadingBuiltinId === m.tag)),
          )
          const isDeleting = Boolean(
            deletingBuiltinId && (deletingBuiltinId === m.id || (m.tag && deletingBuiltinId === m.tag)),
          )

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
                      Descargado ({localInfo?.disk_size_mb ?? 0} MB)
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200">
                      No descargado ({m.size})
                    </span>
                  )}
                  {isSelected && (
                    <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
                      Seleccionado
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
                  {m.description}
                </p>

                <p className="text-xs text-slate-400 font-medium pt-0.5 flex items-center gap-2">
                  <span>Tamaño estimado: {m.size}</span>
                  <span>•</span>
                  <span>Ventana de Contexto: {m.tokens}</span>
                </p>
              </div>

              <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                {isDownloaded ? (
                  <>
                    {handleDeleteBuiltinModel && (
                      <button
                        type="button"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteBuiltinModel(m.id)}
                        title="Eliminar archivo del modelo para liberar espacio en disco"
                        className="inline-flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition cursor-pointer disabled:opacity-50"
                      >
                        {isDeleting ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                        Borrar
                      </button>
                    )}

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
                  <>
                    {handleDownloadBuiltinModel && (
                      isDownloading ? (
                        <button
                          type="button"
                          disabled
                          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#002777] bg-blue-50 border border-blue-200"
                        >
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />
                          <span>
                            {downloadTasks[m.id]?.progress ? `${downloadTasks[m.id].progress}%` : 'Descargando…'}
                          </span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleDownloadBuiltinModel(m.id)}
                          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-[#002777] bg-blue-50 hover:bg-blue-100 border border-blue-200 transition cursor-pointer"
                        >
                          <Download className="h-3.5 w-3.5 text-[#002777]" />
                          <span>Descargar ({m.size})</span>
                        </button>
                      )
                    )}


                    <button
                      type="button"
                      onClick={() => setModel(m.id)}
                      className={[
                        'px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer',
                        isSelected
                          ? 'bg-[#002777] text-white font-bold'
                          : 'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700',
                      ].join(' ')}
                    >
                      {isSelected ? 'Activo' : 'Seleccionar'}
                    </button>
                  </>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
