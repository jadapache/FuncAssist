import { Download, Loader2, RefreshCw, Trash2 } from 'lucide-react'

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
    <div className="space-y-4 pt-2">
      <h4 className="text-sm font-bold text-slate-900">Modelos de IA Integrados (Locales)</h4>

      {pullStatusMsg ? (
        <div className="rounded-xl bg-blue-50 border border-blue-200 p-3 text-xs font-medium text-[#002777] flex items-center gap-2">
          <RefreshCw className={`h-4 w-4 shrink-0 ${isPulling ? 'animate-spin text-[#004497]' : 'text-emerald-600'}`} />
          <span>{pullStatusMsg}</span>
        </div>
      ) : null}

      <div className="space-y-3">
        {builtinModelsList.map((m) => {
          const tagToUse = m.tag || m.id
          const downloaded = isModelDownloaded(tagToUse) || isModelDownloaded(m.id)
          const isSelected = model === m.id || model === m.tag
          const isCurrentlyPulling = isPulling && (pullingModelTag === m.tag || pullingModelTag === m.id)
          const isDeleting = deletingModelTag === m.tag || deletingModelTag === m.id

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
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <h5 className="font-bold text-slate-900 text-base">{m.name}</h5>
                  {downloaded ? (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Descargado ({m.size})
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
                  <span>Tamaño: {m.size}</span>
                  <span>•</span>
                  <span>Contexto / Tokens: {m.tokens}</span>
                </p>
              </div>

              <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                {downloaded ? (
                  <>
                    {handleDeleteModel && (
                      <button
                        type="button"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteModel(tagToUse)}
                        title="Eliminar modelo para liberar espacio en disco"
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
                    <button
                      type="button"
                      disabled={isCurrentlyPulling}
                      onClick={() => void handlePullModel(tagToUse)}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-[#002777] bg-blue-50 hover:bg-blue-100 border border-blue-200 transition cursor-pointer disabled:opacity-50"
                    >
                      {isCurrentlyPulling ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />
                          <span>Descargando…</span>
                        </>
                      ) : (
                        <>
                          <Download className="h-3.5 w-3.5 text-[#002777]" />
                          <span>Descargar ({m.size})</span>
                        </>
                      )}
                    </button>

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
