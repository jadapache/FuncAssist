import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Database, FileText, Layers, ShieldCheck } from 'lucide-react'
import { SourceCodeIntegrationsPanel } from '../../../features/settings/components/SourceCodeIntegrationsPanel'
import { KnowledgeBaseSection } from '../../../features/settings/components/KnowledgeBaseSection'
import { TemplatesPanel } from '../../../features/settings/components/TemplatesPanel'
import { UserApprovalsPanel } from '../../../features/settings/components/UserApprovalsPanel'
import { useIntegrationsManager } from '../../../features/settings/hooks/useIntegrationsManager'
import { useUserApprovalsManager } from '../../../features/settings/hooks/useUserApprovalsManager'
import type { SettingsTabItem, TabType } from '../../../features/settings/types'
import { PageHeader } from '../../../components/common'
import { useUser } from '../../../context/UserContext'

export const SettingsPage = () => {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useUser()
  const role = user?.user_role || 'funcional'
  const isAdmin = role === 'admin'

  const [activeTab, setActiveTab] = useState<TabType>(() => {
    const t = new URLSearchParams(window.location.search).get('tab')
    if (
      t === 'integrations' ||
      t === 'templates' ||
      t === 'knowledge' ||
      t === 'approvals'
    ) {
      return t as TabType
    }
    if (
      window.location.search.includes('github=') ||
      window.location.search.includes('gitlab=')
    ) {
      return 'integrations'
    }
    return 'knowledge'
  })

  const integrationsManager = useIntegrationsManager({ enabled: activeTab === 'integrations' })
  const userApprovalsManager = useUserApprovalsManager({ enabled: isAdmin && activeTab === 'approvals' })

  const [templatesMounted, setTemplatesMounted] = useState(activeTab === 'templates')
  const [knowledgeMounted, setKnowledgeMounted] = useState(activeTab === 'knowledge')
  const [integrationsMounted, setIntegrationsMounted] = useState(activeTab === 'integrations')
  const [approvalsMounted, setApprovalsMounted] = useState(activeTab === 'approvals')

  useEffect(() => {
    const tab = searchParams.get('tab')
    if (tab === 'ai_models') {
      navigate('/profile?tab=ai_providers', { replace: true })
      return
    }

    let next: TabType | null = null
    if (
      tab === 'integrations' ||
      tab === 'templates' ||
      tab === 'knowledge' ||
      tab === 'approvals'
    ) {
      next = tab as TabType
    } else if (searchParams.get('github') || searchParams.get('gitlab')) {
      next = 'integrations'
    }

    if (next) {
      setActiveTab(next)
      if (next === 'templates') setTemplatesMounted(true)
      if (next === 'knowledge') setKnowledgeMounted(true)
      if (next === 'integrations') setIntegrationsMounted(true)
      if (next === 'approvals') setApprovalsMounted(true)
    }
  }, [navigate, searchParams])

  const canSeeIntegrations = ['admin', 'pm', 'funcional', 'qa'].includes(role)

  const TABS: SettingsTabItem[] = [
    {
      id: 'knowledge',
      label: 'Base de Conocimiento',
      subtitle: 'Almacenamiento PostgreSQL RAG (Full-Text & Vector)',
      icon: Database,
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
          label: 'Integraciones RAG',
          subtitle: 'GitHub, GitLab (Contexto de código)',
          icon: Layers,
          badgeCount: integrationsManager.connectedCount,
        },
      ]
      : []),
    ...(isAdmin
      ? [
        {
          id: 'approvals' as TabType,
          label: 'Solicitudes de Acceso',
          subtitle: 'Aprobación de nuevos usuarios',
          icon: ShieldCheck,
          badgeCount: userApprovalsManager.pendingRequests.length,
        },
      ]
      : []),
  ]

  return (
    <div className="space-y-8 pb-12">
      <PageHeader
        eyebrow="SISTEMA & PREFERENCIAS"
        title="Configuración del Sistema"
        subtitle="Administra la base de conocimiento, plantillas, integraciones de código fuente y accesos de usuario."
      />

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
                if (t.id === 'templates') setTemplatesMounted(true)
                if (t.id === 'knowledge') setKnowledgeMounted(true)
                if (t.id === 'integrations') setIntegrationsMounted(true)
                if (t.id === 'approvals') setApprovalsMounted(true)
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

      {/* Tab Panels - lazy mount to avoid re-fetching on tab switch */}
      <div className={activeTab === 'knowledge' ? 'block' : 'hidden'}>
        {knowledgeMounted && <KnowledgeBaseSection />}
      </div>
      <div className={activeTab === 'templates' ? 'block' : 'hidden'}>
        {templatesMounted && <TemplatesPanel />}
      </div>
      {canSeeIntegrations && (
        <div className={activeTab === 'integrations' ? 'block' : 'hidden'}>
          {integrationsMounted && (
            <SourceCodeIntegrationsPanel integrationsManager={integrationsManager} />
          )}
        </div>
      )}
      {isAdmin && (
        <div className={activeTab === 'approvals' ? 'block' : 'hidden'}>
          {approvalsMounted && (
            <UserApprovalsPanel userApprovalsManager={userApprovalsManager} />
          )}
        </div>
      )}
    </div>
  )
}
