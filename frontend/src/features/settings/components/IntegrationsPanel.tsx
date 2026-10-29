import { useMemo, useState } from 'react'
import { Plus, Search } from 'lucide-react'
import { useIntegrationsManager } from '../hooks/useIntegrationsManager'
import {
  IntegrationMarketplaceCard,
  type MarketplaceIntegrationItem,
} from './integrations/IntegrationMarketplaceCard'
import { IntegrationConfigModal } from './integrations/IntegrationConfigModal'
import { RequestIntegrationModal } from './integrations/RequestIntegrationModal'
import { api } from '../../../api/client'
import type { IntegrationInfo } from '../../../types'

export type IntegrationsPanelProps = {
  integrationsManager?: ReturnType<typeof useIntegrationsManager>
}

type FilterTab = 'all' | 'available' | 'connected'

const CATALOG_DEFINITIONS: Array<{
  id: string
  name: string
  description: string
  isCoreBackend: boolean
}> = [
  {
    id: 'trello',
    name: 'Trello',
    description: 'Visual project management using boards, lists, and cards for flexible task tracking.',
    isCoreBackend: false,
  },
  {
    id: 'jira',
    name: 'Jira',
    description: 'Manage complex projects with advanced issue tracking and agile planning capabilities.',
    isCoreBackend: true,
  },
  {
    id: 'confluence',
    name: 'Confluence',
    description: 'Collaborative team workspace for technical documentation, meeting notes, and PRDs.',
    isCoreBackend: false,
  },

]

export const IntegrationsPanel = ({ integrationsManager: externalManager }: IntegrationsPanelProps) => {
  const internalManager = useIntegrationsManager()
  const {
    integrations,
    loadIntegrations,
    busyIntegrationId,
    handleOAuthConnect,
    handleDisconnect,
    handlePatConnected,
  } = externalManager || internalManager

  const [searchQuery, setSearchQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all')
  const [selectedIntegration, setSelectedIntegration] = useState<IntegrationInfo | null>(null)
  const [isConfigOpen, setIsConfigOpen] = useState(false)
  const [isRequestModalOpen, setIsRequestModalOpen] = useState(false)

  // Merge real backend integrations with catalog definitions
  const marketplaceItems: MarketplaceIntegrationItem[] = useMemo(() => {
    return CATALOG_DEFINITIONS.map((def) => {
      const real = integrations.find((i) => i.id === def.id)
      const connected = Boolean(real?.status === 'connected')
      return {
        id: def.id,
        name: def.name,
        description: def.description,
        connected,
        isCoreBackend: def.isCoreBackend,
        accountLabel: real?.account_label,
        workspaceLabel: real?.workspace_label,
      }
    })
  }, [integrations])

  // const connectedCount = marketplaceItems.filter((i) => i.connected).length

  // Filter items based on search and active tab
  const filteredItems = useMemo(() => {
    return marketplaceItems.filter((item) => {
      const matchesSearch =
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description.toLowerCase().includes(searchQuery.toLowerCase())

      if (!matchesSearch) return false

      if (activeFilter === 'connected') return item.connected
      if (activeFilter === 'available') return !item.connected
      return true
    })
  }, [marketplaceItems, searchQuery, activeFilter])

  const handleOpenDetails = (item: MarketplaceIntegrationItem) => {
    const existing = integrations.find((i) => i.id === item.id)
    const integrationObj: IntegrationInfo = existing || {
      id: item.id,
      name: item.name,
      description: item.description,
      auth_method: 'pat',
      connected: item.connected,
      status: item.connected ? 'connected' : 'not_configured',
    }
    setSelectedIntegration(integrationObj)
    setIsConfigOpen(true)
  }

  const handleToggle = async (item: MarketplaceIntegrationItem) => {
    if (item.connected) {
      if (window.confirm(`¿Deseas desconectar ${item.name}?`)) {
        await handleDisconnect(item.id)
        await loadIntegrations()
      }
    } else {
      handleOpenDetails(item)
    }
  }

  return (
    <div className="space-y-7">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-4">
        <button
          type="button"
          onClick={() => setIsRequestModalOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 transition cursor-pointer self-start sm:self-auto"
        >
          <Plus className="h-4 w-4" />
          <span>Solicitar integración</span>
        </button>
      </div>

      {/* All Integrations Section */}
      <section className="space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <h3 className="text-lg font-bold text-slate-900">Todas las integraciones</h3>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative min-w-[220px]">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Búscar integraciones..."
                className="w-full rounded-xl border border-slate-200 bg-white py-1.5 pl-8 pr-3 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-2xs"
              />
            </div>

            {/* Segmented Filter Buttons */}
            <div className="flex items-center rounded-xl bg-slate-100 p-1 border border-slate-200/60">
              <button
                type="button"
                onClick={() => setActiveFilter('all')}
                className={`rounded-lg px-3 py-1 text-xs font-semibold transition cursor-pointer ${
                  activeFilter === 'all'
                    ? 'bg-white text-slate-900 shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Disponibles
              </button>
              <button
                type="button"
                onClick={() => setActiveFilter('connected')}
                className={`rounded-lg px-3 py-1 text-xs font-semibold transition cursor-pointer ${
                  activeFilter === 'connected'
                    ? 'bg-white text-slate-900 shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Conectadas
              </button>
            </div>
          </div>
        </div>

        {/* Integration Cards Grid */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filteredItems.map((item) => (
            <IntegrationMarketplaceCard
              key={item.id}
              item={item}
              busy={busyIntegrationId === item.id}
              onToggle={handleToggle}
              onDetails={handleOpenDetails}
            />
          ))}
        </div>

        {filteredItems.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/50 p-8 text-center text-xs text-slate-500">
            No se encontraron integraciones con el filtro o término de búsqueda aplicado.
          </div>
        )}
      </section>

      {/* Integration Configuration Modal */}
      <IntegrationConfigModal
        integration={selectedIntegration}
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        onRefresh={loadIntegrations}
        onConnectOAuth={handleOAuthConnect}
        onConnectPat={async (id, token, email, url) => {
          await api.connectWithPat(id, { token, email, base_url: url })
          await handlePatConnected(id, id)
        }}
        onDisconnect={handleDisconnect}
      />

      {/* Request Integration Modal */}
      <RequestIntegrationModal
        isOpen={isRequestModalOpen}
        onClose={() => setIsRequestModalOpen(false)}
      />
    </div>
  )
}
