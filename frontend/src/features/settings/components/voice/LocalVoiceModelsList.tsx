import { HardDrive } from 'lucide-react'

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
}

interface ModelCardProps {
  item: LocalVoiceModelItem
  isSelected: boolean
  onSelect: () => void
}

export const LocalVoiceModelCard = ({ item, isSelected, onSelect }: ModelCardProps) => {
  return (
    <div
      onClick={onSelect}
      className={[
        'flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl transition-all cursor-pointer',
        isSelected
          ? 'border-2 border-[#002777] bg-blue-50/20 shadow-xs'
          : 'border border-slate-200 bg-white hover:border-slate-300',
      ].join(' ')}
    >
      <div className="space-y-1.5 flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h5 className="font-bold text-slate-900 text-base">{item.name}</h5>
          <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-[#002777] border border-blue-200">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
            ONNX Runtime Web
          </span>
          {isSelected && (
            <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
              Activo
            </span>
          )}
        </div>

        <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
          {item.description}
        </p>

        <p className="text-xs text-slate-400 font-medium pt-0.5 flex items-center gap-2">
          <span>Tamaño estimado: {item.size || 'Variable'}</span>
          {item.accuracy && (
            <>
              <span>•</span>
              <span>Precisión: {item.accuracy}</span>
            </>
          )}
        </p>
      </div>

      <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={onSelect}
          className={[
            'px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer',
            isSelected
              ? 'bg-[#002777] text-white font-bold shadow-xs'
              : 'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700',
          ].join(' ')}
        >
          {isSelected ? 'Activo' : 'Seleccionar'}
        </button>
      </div>
    </div>
  )
}

export const LocalVoiceModelsList = ({
  localVoiceModelsList,
  model,
  setModel,
}: LocalVoiceModelsListProps) => {
  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[#002777]" />
            <span>Modelos de IA Integrados (ONNX Runtime Web)</span>
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            Modelos de transcripción ejecutados directamente en tu navegador (WebGPU / CPU Wasm). Sin enviar audio a servidores externos ni descargas en el backend.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {localVoiceModelsList.map((m) => {
          const isSelected =
            model === m.id ||
            model === `whisper-${m.id}` ||
            (model === 'base' && m.id === 'whisper-base') ||
            (model === 'tiny' && m.id === 'whisper-tiny') ||
            (model === 'small' && m.id === 'whisper-small') ||
            (model === 'large-v3-turbo' && m.id === 'whisper-large-v3-turbo')
          return (
            <LocalVoiceModelCard
              key={m.id}
              item={m}
              isSelected={isSelected}
              onSelect={() => setModel(m.id)}
            />
          )
        })}
      </div>
    </div>
  )
}
