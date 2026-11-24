import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import type { IntegrationInfo } from '../../../types'
import { GitHostingReposPanel } from '../../../features/integrations'
import { JiraIssuesPreview } from '../../../features/integrations'
import { JiraOAuthSetup } from '../../../features/integrations'
import { JiraProjectsPanel } from '../../../features/integrations'
import { GitOAuthSetup as OAuthSetup } from '../../../features/integrations'
import { StatusPill } from './StatusPill'

export type IntegrationCardProps = {
  integration: IntegrationInfo
  busy: boolean
  onOAuth: () => void
  onDisconnect: () => void
  onTest: () => void
  onConnected: () => Promise<void>
  onOAuthSaved: () => Promise<void>
  onError: (message: string) => void
}

export const IntegrationCard = ({
  integration,
  busy,
  onOAuth,
  onDisconnect,
  onTest,
  onConnected,
  onOAuthSaved,
  onError,
}: IntegrationCardProps) => {
  const connected = integration.status === 'connected'
  const [showConnectForm, setShowConnectForm] = useState(false)

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
          {integration.account_label ? (
            <p>
              <span className="font-semibold text-slate-500">Cuenta vinculada: </span>
              <span className="font-medium text-slate-800">{integration.account_label}</span>
            </p>
          ) : null}
          {integration.details?.auth_method ? (
            <p>
              <span className="font-semibold text-slate-500">Método de autenticación: </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 uppercase">
                {String(integration.details.auth_method)}
              </span>
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3">
        {connected ? (
          <>
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
            <button
              type="button"
              onClick={() => setShowConnectForm(true)}
              disabled={busy}
              className="btn-secondary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
              aria-label={`Cambiar cuenta ${integration.name}`}
            >
              Cambiar cuenta
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setShowConnectForm(true)}
            className="btn-primary text-xs py-2.5 px-5 cursor-pointer"
            aria-label={`Conectar ${integration.name}`}
          >
            Conectar {integration.name}
          </button>
        )}
      </div>

      {connected && integration.id === 'jira' ? (
        <div className="pt-2 border-t border-[var(--color-border)] space-y-4">
          <JiraProjectsPanel
            siteUrl={integration.workspace_label}
            onSaved={() => void onConnected()}
            onError={onError}
          />
          <JiraIssuesPreview onError={onError} />
        </div>
      ) : null}

      {connected && integration.id === 'github' ? (
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

      {connected && integration.id === 'gitlab' ? (
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

      {showConnectForm ? (
        <div className="mt-6 border-t border-[var(--color-border)] pt-5 space-y-4">
          <div className="mt-4">
            {integration.id === 'jira' ? (
              <JiraOAuthSetup
                onSaved={onOAuthSaved}
                onContinueOAuth={onOAuth}
                onCancel={() => setShowConnectForm(false)}
              />
            ) : integration.id === 'github' ? (
              <OAuthSetup
                provider="github"
                title="GitHub OAuth"
                docsUrl="https://github.com/settings/developers"
                docsLabel="github.com/settings/developers"
                defaultRedirect="http://127.0.0.1:6728/api/integrations/github/callback"
                onSaved={onOAuthSaved}
                onContinueOAuth={onOAuth}
                onCancel={() => setShowConnectForm(false)}
              />
            ) : integration.id === 'gitlab' ? (
              <OAuthSetup
                provider="gitlab"
                title="GitLab OAuth"
                docsUrl="https://gitlab.com/-/user_settings/applications"
                docsLabel="gitlab.com user applications"
                defaultRedirect="http://127.0.0.1:6728/api/integrations/gitlab/callback"
                showBaseUrl
                onSaved={onOAuthSaved}
                onContinueOAuth={onOAuth}
                onCancel={() => setShowConnectForm(false)}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  )
}
