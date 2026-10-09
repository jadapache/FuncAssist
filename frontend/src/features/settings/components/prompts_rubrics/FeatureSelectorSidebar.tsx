import { Search } from 'lucide-react'
import type { AIPromptTemplate, AIRubric } from '../../../../api/client'
import type { FeatureMeta } from './types'

interface FeatureSelectorSidebarProps {
  features: FeatureMeta[]
  selectedFeature: string
  promptsList: AIPromptTemplate[]
  rubricsList: AIRubric[]
  searchQuery: string
  onSearchChange: (query: string) => void
  onSelectFeature: (featureId: string) => void
}

export const FeatureSelectorSidebar = ({
  features,
  selectedFeature,
  promptsList,
  rubricsList,
  searchQuery,
  onSearchChange,
  onSelectFeature,
}: FeatureSelectorSidebarProps) => {
  return (
    <div className="card p-4 bg-white border border-slate-200 rounded-2xl shadow-xs space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
          Funcionalidades ({features.length})
        </span>
        <span className="text-[10px] text-slate-400">
          {promptsList.length} prompts / {rubricsList.length} rúbricas
        </span>
      </div>

      {/* Search filter input */}
      <div className="relative">
        <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Buscar funcionalidad..."
          className="input-field !pl-9 text-xs py-1.5 border border-slate-200 rounded-xl"
        />
      </div>

      {/* Features List */}
      <div className="space-y-1.5 max-h-[600px] overflow-y-auto pr-1">
        {features.map((f) => {
          const isSelected = selectedFeature === f.id
          const pItem = promptsList.find((p) => p.feature === f.id)
          const rItem = rubricsList.find((r) => r.feature === f.id)

          return (
            <button
              key={f.id}
              type="button"
              onClick={() => onSelectFeature(f.id)}
              className={[
                'w-full text-left p-3 rounded-xl transition-all cursor-pointer border flex flex-col gap-1',
                isSelected
                  ? 'bg-blue-50/90 border-[#002777] shadow-xs'
                  : 'bg-white hover:bg-slate-50 border-slate-200/80 text-slate-700',
              ].join(' ')}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={[
                    'text-xs font-bold truncate',
                    isSelected ? 'text-[#002777]' : 'text-slate-900',
                  ].join(' ')}
                >
                  {f.title}
                </span>
                <code className="text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 shrink-0">
                  {f.id}
                </code>
              </div>

              <p className="text-[11px] text-slate-500 line-clamp-1">{f.description}</p>

              <div className="flex items-center gap-2 pt-1 text-[10px]">
                <span className="inline-flex items-center gap-1 text-slate-500 font-mono">
                  P: v{pItem?.version || 1}
                </span>
                <span className="text-slate-300">•</span>
                <span className="inline-flex items-center gap-1 text-slate-500 font-mono">
                  R: v{rItem?.version || 1}
                </span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

