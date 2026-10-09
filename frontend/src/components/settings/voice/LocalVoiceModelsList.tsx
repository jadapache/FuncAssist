import { useState } from 'react'
import { Download, HardDrive, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import type { LocalWhisperModelInfo } from '../../../api/client'

export interface LocalVoiceModelItem {
  id: string
  name: string
  tag?: string
  description: string
  size: string
  accuracy?: string
  provider?: string
  engine?: string
  is_downloaded?: boolean
  disk_size_mb?: number
}

export interface LocalVoiceModelsListProps {
  localVoiceModelsList: LocalVoiceModelItem[]
  model: string
  setModel: (m: string) => void
  localWhisperModels?: LocalWhisperModelInfo[]
  downloadingWhisperId?: string | null
  deletingWhisperId?: string | null
  fetchingWhisperModels?: boolean
  fetchLocalWhisperModels?: () => Promise<void>
  handleDownloadWhisperModel?: (modelId: string) => Promise<void>
  handleDeleteWhisperModel?: (modelId: string) => Promise<void>
  downloadTasks?: Record<string, { progress: number; speedOrSize?: string | null; stageText?: string }>
}

export const LocalVoiceModelsList = ({
  localVoiceModelsList,
  model,
  setModel,
  localWhisperModels = [],
  downloadingWhisperId = null,
  deletingWhisperId = null,
  fetchingWhisperModels = false,
  fetchLocalWhisperModels,
  handleDownloadWhisperModel,
  handleDeleteWhisperModel,
  downloadTasks = {},
}: LocalVoiceModelsListProps) => {
  const [engineFilter, setEngineFilter] = useState<string>('all')

  const filteredList = localVoiceModelsList.filter((m) => {
    if (engineFilter === 'all') return true
    if (engineFilter === 'onnx') return m.provider === 'onnx' || m.id.startsWith('parakeet') || m.id.startsWith('sense-voice') || m.id.includes('onnx')
    if (engineFilter === 'faster-whisper') return m.provider === 'faster-whisper' || m.id.startsWith('fw-')
    if (engineFilter === 'moonshine') return m.provider === 'moonshine' || (m.id.startsWith('moonshine') && !m.id.includes('onnx'))
    if (engineFilter === 'whisper') return (m.provider === 'builtin' || m.provider === 'local') && !m.id.startsWith('fw-') && !m.id.startsWith('moonshine') && !m.id.startsWith('parakeet') && !m.id.startsWith('sense-voice')
    return true
  })

  return (
    <div className="space-y-4 pt-2">
      {/* Encabezado de Modelos Locales idéntico a WritingModelSection / BuiltinModelsList */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[#002777]" />
            <span>Modelos de IA Integrados (Local)</span>
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            Modelos de transcripción (ONNX Runtime, Faster Whisper, Moonshine, Whisper) ejecutados directamente en tu GPU/CPU de forma privada sin enviar audio a internet.
          </p>
        </div>

        {fetchLocalWhisperModels && (
          <button
            type="button"
            onClick={() => void fetchLocalWhisperModels()}
            disabled={fetchingWhisperModels}
            title="Actualizar estado de modelos en disco"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition cursor-pointer self-start sm:self-auto disabled:opacity-50"
          >
            <RefreshCw className={['h-3.5 w-3.5', fetchingWhisperModels ? 'animate-spin' : ''].join(' ')} />
            <span>Actualizar</span>
          </button>
        )}
      </div>

      {/* Pestañas de Filtrado por Motor / Arquitectura */}
      <div className="flex flex-wrap items-center gap-1.5 pt-1">
        {[
          { id: 'all', label: `Todos (${localVoiceModelsList.length})` },
          { id: 'onnx', label: 'ONNX Runtime' },
          { id: 'faster-whisper', label: 'Faster Whisper' },
          { id: 'whisper', label: 'Whisper' },
          { id: 'moonshine', label: 'Moonshine' },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setEngineFilter(tab.id)}
            className={[
              'px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer',
              engineFilter === tab.id
                ? 'bg-[#002777] text-white shadow-xs'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
            ].join(' ')}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Lista de Modelos */}
      <div className="space-y-3">
        {filteredList.map((m) => {
          const isSelected = model === m.id || model === `whisper-${m.id}`
          const cleanId = m.id.replace('whisper-', '')
          const localInfo = localWhisperModels.find((lm) => lm.id === cleanId || lm.id === m.id)
          const isDownloaded = Boolean(
            m.is_downloaded || localInfo?.is_downloaded,
          )
          const isDownloading = Boolean(
            downloadingWhisperId && (downloadingWhisperId === cleanId || downloadingWhisperId === m.id),
          )
          const isDeleting = Boolean(
            deletingWhisperId && (deletingWhisperId === cleanId || deletingWhisperId === m.id),
          )
          const catalogMb = typeof m.disk_size_mb === 'number' ? m.disk_size_mb : 0
          const diskSizeStr =
            localInfo && localInfo.disk_size_mb > 0
              ? `${localInfo.disk_size_mb} MB`
              : catalogMb > 0
                ? `${catalogMb} MB`
                : m.size || '75 MB'

          const engineLabel =
            m.provider === 'onnx' || m.id.startsWith('parakeet') || m.id.startsWith('sense-voice') || m.id.includes('onnx')
              ? 'ONNX Runtime'
              : m.id.startsWith('fw-') || m.provider === 'faster-whisper'
                ? 'Faster Whisper'
                : m.id.startsWith('moonshine') || m.provider === 'moonshine'
                  ? 'Moonshine'
                  : 'Whisper'

          const taskInfo =
            downloadTasks[cleanId] ||
            downloadTasks[m.id] ||
            downloadTasks[`whisper-${cleanId}`]

          return (
            <div
              key={m.id}
              onClick={() => setModel(m.id)}
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
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-mono font-semibold text-slate-700 border border-slate-200">
                    {engineLabel}
                  </span>
                  {isDownloaded ? (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Descargado ({diskSizeStr})
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200">
                      No descargado ({m.size || 'Local'})
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
                  <span>Tamaño estimado: {m.size || 'Variable'}</span>
                  {m.accuracy && (
                    <>
                      <span>•</span>
                      <span>Precisión: {m.accuracy}</span>
                    </>
                  )}
                </p>
              </div>

              {/* Botones de Acción */}
              <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                {isDownloaded ? (
                  <>
                    {handleDeleteWhisperModel && (
                      <button
                        type="button"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteWhisperModel(m.id)}
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
                    {handleDownloadWhisperModel && (
                      isDownloading ? (
                        <button
                          type="button"
                          disabled
                          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#002777] bg-blue-50 border border-blue-200"
                        >
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#002777]" />
                          <span>
                            {taskInfo?.progress ? `${taskInfo.progress}%` : 'Descargando…'}
                          </span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleDownloadWhisperModel(m.id)}
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
