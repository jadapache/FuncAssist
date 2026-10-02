import { Check, Download, RefreshCw, Trash2 } from 'lucide-react'

export interface BuiltinModelItem {
  id: string
  name: string
  tag: string
  description: string
  size: string
  tokens: string
}

export interface BuiltinModelsListProps {
  builtinModelsList: BuiltinModelItem[]
  model: string
  setModel: (m: string) => void
  isPulling: boolean
  pullingModelTag: string | null
  deletingModelTag?: string | null
  pullStatusMsg: string | null
  handlePullModel: (tag: string) => Promise<void>
  handleDeleteModel?: (tag: string) => Promise<void>
  isModelDownloaded: (tag: string) => boolean
}

export const BuiltinModelsList = ({
  builtinModelsList,
  model,
  setModel,
  isPulling,
  pullingModelTag,
  deletingModelTag,
  pullStatusMsg,
  handlePullModel,
  handleDeleteModel,
  isModelDownloaded,
}: BuiltinModelsListProps) => {
  return (
    <div className="space-y-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-slate-800 uppercase tracking-wider">
          Modelos de IA Integrada Disponibles
        </label>
        <span className="text-[10px] text-slate-500">Ejecución 100% local en servidor QA_MGMT</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {builtinModelsList.map((bm) => {
          const isSelected = model === bm.tag || model === bm.id
          const downloaded = isModelDownloaded(bm.tag)
          const isThisPulling = isPulling && pullingModelTag === bm.tag
          const isThisDeleting = deletingModelTag === bm.tag

          return (
            <div
              key={bm.id}
              onClick={() => downloaded && setModel(bm.tag)}
              className={[
                'p-4 rounded-xl border transition-all flex flex-col justify-between gap-3 cursor-pointer',
                isSelected
                  ? 'bg-white border-[#002777] ring-2 ring-[#002777]/20 shadow-xs'
                  : downloaded
                  ? 'bg-white border-slate-200 hover:border-slate-300'
                  : 'bg-white/60 border-slate-200 opacity-75',
              ].join(' ')}
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-bold text-slate-900 truncate">{bm.name}</h4>
                  {isSelected && (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[#002777] text-white">
                      <Check className="h-2.5 w-2.5" />
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-500 mt-1 line-clamp-2 leading-relaxed">
                  {bm.description}
                </p>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-[10px] text-slate-500 font-mono">
                <span>{bm.size}</span>
                <span>{bm.tokens}</span>
              </div>

              <div className="pt-1">
                {downloaded ? (
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-medium border border-emerald-200">
                      ✓ Descargado y Listo
                    </span>
                    {handleDeleteModel && (
                      <button
                        type="button"
                        disabled={isThisDeleting}
                        onClick={(e) => {
                          e.stopPropagation()
                          void handleDeleteModel(bm.tag)
                        }}
                        className="text-slate-400 hover:text-red-600 p-1 cursor-pointer transition"
                        title="Eliminar modelo local"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={isPulling}
                    onClick={(e) => {
                      e.stopPropagation()
                      void handlePullModel(bm.tag)
                    }}
                    className="w-full btn btn-secondary text-xs py-1.5 inline-flex items-center justify-center gap-1.5 bg-white border border-blue-200 text-[#002777] font-semibold cursor-pointer disabled:opacity-50"
                  >
                    {isThisPulling ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>Descargando...</span>
                      </>
                    ) : (
                      <>
                        <Download className="h-3.5 w-3.5" />
                        <span>Descargar Modelo</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {isPulling && pullStatusMsg && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-[#002777] flex items-center gap-2">
          <RefreshCw className="h-3.5 w-3.5 animate-spin shrink-0" />
          <span className="font-mono text-[11px]">{pullStatusMsg}</span>
        </div>
      )}
    </div>
  )
}

