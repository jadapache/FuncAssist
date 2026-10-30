import { Settings } from 'lucide-react'
import { IntegrationLogo } from './IntegrationLogo'

export interface MarketplaceIntegrationItem {
  id: string
  name: string
  description: string
  connected: boolean
  isCoreBackend?: boolean
  accountLabel?: string
  workspaceLabel?: string
}

interface IntegrationMarketplaceCardProps {
  item: MarketplaceIntegrationItem
  busy?: boolean
  onToggle: (item: MarketplaceIntegrationItem) => void
  onDetails: (item: MarketplaceIntegrationItem) => void
}

export const IntegrationMarketplaceCard = ({
  item,
  busy = false,
  onToggle,
  onDetails,
}: IntegrationMarketplaceCardProps) => {
  return (
    <div className="group flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs hover:shadow-md transition-all duration-200">
      <div>
        <div className="flex items-center justify-between">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-50 border border-slate-100 p-2 shadow-2xs">
            <IntegrationLogo id={item.id} className="h-6 w-6" />
          </div>
        </div>

        <div className="mt-4">
          <h3 className="text-base font-bold text-slate-900 group-hover:text-blue-700 transition-colors">
            {item.name}
          </h3>
          <p className="mt-1 text-xs text-slate-500 line-clamp-2 leading-relaxed min-h-[36px]">
            {item.description}
          </p>
        </div>
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
        <button
          type="button"
          onClick={() => onDetails(item)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200/90 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 hover:border-slate-300 transition cursor-pointer"
        >
          <Settings className="h-3.5 w-3.5 text-slate-500" />
          <span>Detalles</span>
        </button>

        <button
          type="button"
          role="switch"
          aria-checked={item.connected}
          disabled={busy}
          onClick={() => onToggle(item)}
          aria-label={`Activar o desactivar ${item.name}`}
          className={[
            'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2',
            item.connected ? 'bg-indigo-600' : 'bg-slate-200',
            busy ? 'opacity-50 cursor-wait' : '',
          ].join(' ')}
        >
          <span
            className={[
              'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out',
              item.connected ? 'translate-x-5' : 'translate-x-0',
            ].join(' ')}
          />
        </button>
      </div>
    </div>
  )
}
