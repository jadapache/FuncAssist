import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Cpu, FileText, Layers } from 'lucide-react'
import { AiModelsPanel } from '../../components/settings/AiModelsPanel'
import { IntegrationsPanel } from '../../components/settings/IntegrationsPanel'
import { TemplatesPanel } from '../../components/settings/TemplatesPanel'
import { useIntegrationsManager } from '../../components/settings/hooks/useIntegrationsManager'
import type { SettingsTabItem, TabType } from '../../components/settings/types'
import { useUser } from '../../context/UserContext'

export const SettingsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useUser()
  const role = user?.user_role || 'admin'

  const [activeTab, setActiveTab] = useState<TabType>(() => {
    const t = new URLSearchParams(window.location.search).get('tab')
    if (t === 'integrations' || t === 'ai_models' || t === 'templates') {
      return t as TabType
    }
    if (
      window.location.search.includes('jira=') ||
      window.location.search.includes('github=') ||
      window.location.search.includes('gitlab=')
    ) {
      return 'integrations'
    }
    return 'ai_models'
  })

  // Integrations manager to populate badge count
  const integrationsManager = useIntegrationsManager()

  useEffect(() => {
    const tab = searchParams.get('tab')
    if (tab === 'integrations' || tab === 'ai_models' || tab === 'templates') {
      setActiveTab(tab as TabType)
    } else if (searchParams.get('jira') || searchParams.get('github') || searchParams.get('gitlab')) {
      setActiveTab('integrations')
    }
  }, [searchParams])

  // Filter tabs based on role if needed (e.g. integrations for admin & pm)
  const canSeeIntegrations = ['admin', 'pm'].includes(role)

  const TABS: SettingsTabItem[] = [
    {
      id: 'ai_models',
      label: 'Modelos de IA',
      subtitle: 'Configuración de modelos locales y APIs',
      icon: Cpu,
    },
    {
      id: 'templates',
      label: 'Plantillas',
      subtitle: 'Plantillas corporativas (.doc, .docx, .xlsx)',
      icon: FileText,
    },
    ...(canSeeIntegrations
      ? [
          {
            id: 'integrations' as TabType,
            label: 'Integraciones',
            subtitle: 'Jira Software, GitHub, GitLab',
            icon: Layers,
            badgeCount: integrationsManager.connectedCount,
          },
        ]
      : []),
  ]

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#002777]">Sistema & Preferencias</p>
        </div>
        <h1 className="page-title">Configuración del Sistema</h1>
        <p className="page-subtitle">
          Administra los modelos de IA, plantillas corporativas e integraciones con repositorios.
        </p>
      </header>

      {/* Nav Tabs Bar */}
      <nav className="flex flex-wrap gap-2 rounded-2xl border border-[var(--color-border)] bg-slate-100/70 p-1.5 shadow-sm">
        {TABS.map((t) => {
          const Icon = t.icon
          const isActive = activeTab === t.id
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                setActiveTab(t.id)
                setSearchParams({ tab: t.id }, { replace: true })
              }}
              className={[
                'flex flex-1 min-w-[200px] items-center gap-3 rounded-xl px-4 py-3 text-left transition-all duration-200 cursor-pointer',
                isActive
                  ? 'bg-white text-[#002777] shadow-md ring-1 ring-black/5 font-bold'
                  : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 font-medium',
              ].join(' ')}
            >
              <div
                className={[
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors',
                  isActive ? 'bg-[#002777] text-white' : 'bg-slate-200/80 text-slate-600',
                ].join(' ')}
              >
                <Icon className="h-5 w-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold truncate">{t.label}</span>
                  {t.badgeCount && t.badgeCount > 0 ? (
                    <span className="inline-flex items-center justify-center rounded-full bg-amber-500 px-2 py-0.5 text-[10px] font-extrabold text-white animate-pulse">
                      {t.badgeCount}
                    </span>
                  ) : null}
                </div>
                <p className="text-[11px] text-slate-500 truncate font-normal">{t.subtitle}</p>
              </div>
            </button>
          )
        })}
      </nav>

      {/* Tab Panels */}
      {activeTab === 'ai_models' && <AiModelsPanel />}
      {activeTab === 'templates' && <TemplatesPanel />}
      {activeTab === 'integrations' && canSeeIntegrations && (
        <IntegrationsPanel integrationsManager={integrationsManager} />
      )}
    </div>
  )
}
