import { RefreshCw } from 'lucide-react'
import type { IntegrationInfo } from '../../../types'
import { GitHostingReposPanel } from '../../../features/integrations'
import { StatusPill } from './StatusPill'
import { ServiceAccountForm } from './ServiceAccountForm'
import { ServiceAccountStatus } from './ServiceAccountStatus'
import { GitHubAppForm } from './GitHubAppForm'
import { GitHubAppStatus } from './GitHubAppStatus'

export type IntegrationCardProps = {
  integration: IntegrationInfo
  busy: boolean
  onDisconnect: () => void
  onTest: () => void
  onConnected: () => Promise<void>
  onError: (message: string) => void
  /** Organization integrations (GitHub, GitLab) can only be managed by an administrator. */
  canManage?: boolean
}

export const IntegrationCard = ({
  integration,
  busy,
  onDisconnect,
  onTest,
  onConnected,
  onError,
  canManage = true,
}: IntegrationCardProps) => {
  const connected = integration.status === 'connected'
  const isGitlab = integration.id === 'gitlab'
  const isGithub = integration.id === 'github'
  const isServiceAccount = integration.details?.auth_method === 'service_account'

  return (
    <article className="card border border-[var(--color-border)] p-6 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">{integration.name}</h2>
          <p className="mt-1 text-sm text-[var(--color-ink-muted)]">{integration.description}</p>
        </div>
        <StatusPill connected={connected} />
      </div>

      {connected ? (
        <div className="rounded-xl bg-slate-50 border border-slate-200/80 p-4 space-y-1.5 text-xs">
          {integration.workspace_label ? (
            <p>
              <span className="font-semibold text-slate-500">Espacio de trabajo / Workspace: </span>
              <span className="font-mono text-slate-800">{integration.workspace_label}</span>
            </p>
          ) : null}
          {isGitlab && isServiceAccount ? (
            <ServiceAccountStatus integration={integration} />
          ) : isGithub && isServiceAccount ? (
            <GitHubAppStatus integration={integration} />
          ) : integration.account_label ? (
            <p>
              <span className="font-semibold text-slate-500">Cuenta vinculada: </span>
              <span className="font-medium text-slate-800">{integration.account_label}</span>
            </p>
          ) : null}
        </div>
      ) : null}

      {!canManage ? (
        <p className="text-xs text-[var(--color-ink-muted)]">
          {connected
            ? 'Esta integración es de la organización y la gestiona un administrador.'
            : 'Esta integración aún no está conectada. Solo un administrador puede conectarla.'}
        </p>
      ) : null}

      {canManage && connected ? (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onTest}
            disabled={busy}
            className="btn-primary text-xs py-2 px-4 disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
            aria-label={`Probar conexión ${integration.name}`}
          >
            {busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : null}
            <span>Probar conexión</span>
          </button>
          <button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            className="rounded-lg border border-[var(--color-bad)] px-4 py-2 text-xs font-semibold text-[var(--color-bad)] hover:bg-red-50 disabled:opacity-50 transition cursor-pointer"
            aria-label={`Desconectar ${integration.name}`}
          >
            Desconectar
          </button>
        </div>
      ) : null}

      {canManage && connected && isGithub ? (
        <div className="pt-2 border-t border-[var(--color-border)]">
          <GitHostingReposPanel
            integrationId="github"
            heading="Repositorios de GitHub"
            description="Solo los repositorios seleccionados están disponibles para las funciones del sistema. Nada se auto-selecciona."
            onSaved={() => void onConnected()}
            onError={onError}
          />
        </div>
      ) : null}

      {canManage && connected && isGitlab ? (
        <div className="pt-2 border-t border-[var(--color-border)]">
          <GitHostingReposPanel
            integrationId="gitlab"
            heading="Proyectos de GitLab"
            description="Solo los proyectos seleccionados están disponibles para las funciones del sistema. Nada se auto-selecciona."
            onSaved={() => void onConnected()}
            onError={onError}
          />
        </div>
      ) : null}

      {canManage && isGitlab ? (
        <div className="pt-2 border-t border-[var(--color-border)]">
          <ServiceAccountForm onConnected={onConnected} onError={onError} />
        </div>
      ) : null}

      {canManage && isGithub ? (
        <div className="pt-2 border-t border-[var(--color-border)]">
          <GitHubAppForm onConnected={onConnected} onError={onError} />
        </div>
      ) : null}
    </article>
  )
}
