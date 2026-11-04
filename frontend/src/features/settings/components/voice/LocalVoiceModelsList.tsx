import { HardDrive } from 'lucide-react'
import {
  getClientAsrModels,
  type ClientAsrModelDefinition,
} from '../../../ai/catalogs/clientCatalog'

export interface LocalVoiceModelsListProps {
  model: string
  setModel: (m: string) => void
}

interface ModelCardProps {
  item: ClientAsrModelDefinition
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
            {item.badge}
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
          <span>Tamaño estimado: {item.downloadSize}</span>
          <span>•</span>
          <span>Precisión: {item.accuracy}</span>
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
  model,
  setModel,
}: LocalVoiceModelsListProps) => {
  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[#002777]" />
            <span>Transcripción en este navegador (Transformers.js / WebGPU)</span>
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            El reconocimiento de voz se realiza directamente en un Web Worker en tu dispositivo. El archivo de audio nunca sale de tu navegador.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {getClientAsrModels().map((m) => {
          const isSelected = model === m.id
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
