import { Layers, RefreshCw } from 'lucide-react'
import { IntegrationsSkeleton } from '../../../components/common'
import { IntegrationCard } from './IntegrationCard'
import { useIntegrationsManager } from '../hooks/useIntegrationsManager'
import { useToast } from '../../../context/ToastContext'

export type IntegrationsPanelProps = {
  integrationsManager?: ReturnType<typeof useIntegrationsManager>
}

export const IntegrationsPanel = ({ integrationsManager: externalManager }: IntegrationsPanelProps) => {
  const internalManager = useIntegrationsManager()
  const {
    loadingIntegrations,
    loadIntegrations,
    busyIntegrationId,
    handleOAuthConnect,
    handleDisconnect,
    handleTest,
    handlePatConnected,
    jira,
    github,
    gitlab,
  } = externalManager || internalManager

  const { toast } = useToast()

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--color-border)] pb-4">
        <div>
          <h2 className="text-xl font-bold text-[var(--color-ink)] flex items-center gap-2">
            <Layers className="h-5 w-5 text-[#002777]" />
            Integraciones de Desarrollo & QA
          </h2>
          <p className="text-xs text-[var(--color-ink-muted)] mt-1">
            Conecta tus cuentas independientemente (Jira Software, GitHub, GitLab) mediante OAuth 2.0 o Personal Access Token.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadIntegrations()}
          disabled={loadingIntegrations}
          className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5 self-start sm:self-auto cursor-pointer"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loadingIntegrations ? 'animate-spin' : ''}`} />
          <span>Actualizar Estado</span>
        </button>
      </div>

      {loadingIntegrations ? (
        <IntegrationsSkeleton />
      ) : (
        <div className="space-y-6">
          {jira ? (
            <IntegrationCard
              integration={jira}
              busy={busyIntegrationId === 'jira'}
              onOAuth={() => void handleOAuthConnect('jira')}
              onDisconnect={() => void handleDisconnect('jira')}
              onTest={() => void handleTest('jira')}
              onPatConnected={() => handlePatConnected('jira', 'Jira')}
              onOAuthSaved={async () => {
                await loadIntegrations()
                toast.success('Credenciales OAuth de Jira guardadas con éxito.')
              }}
              onError={(err) => toast.error(err)}
            />
          ) : null}

          {github ? (
            <IntegrationCard
              integration={github}
              busy={busyIntegrationId === 'github'}
              onOAuth={() => void handleOAuthConnect('github')}
              onDisconnect={() => void handleDisconnect('github')}
              onTest={() => void handleTest('github')}
              onPatConnected={() => handlePatConnected('github', 'GitHub')}
              onOAuthSaved={async () => {
                await loadIntegrations()
                toast.success('Credenciales OAuth de GitHub guardadas con éxito.')
              }}
              onError={(err) => toast.error(err)}
            />
          ) : null}

          {gitlab ? (
            <IntegrationCard
              integration={gitlab}
              busy={busyIntegrationId === 'gitlab'}
              onOAuth={() => void handleOAuthConnect('gitlab')}
              onDisconnect={() => void handleDisconnect('gitlab')}
              onTest={() => void handleTest('gitlab')}
              onPatConnected={() => handlePatConnected('gitlab', 'GitLab')}
              onOAuthSaved={async () => {
                await loadIntegrations()
                toast.success('Credenciales OAuth de GitLab guardadas con éxito.')
              }}
              onError={(err) => toast.error(err)}
            />
          ) : null}
        </div>
      )}
    </div>
  )
}
