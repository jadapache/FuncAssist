import type { FormEvent } from 'react'
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../../../api/client'
import type { AuthMethod, IntegrationInfo } from '../../../types'
import { GitHostingReposPanel } from '../../../features/integrations'
import { JiraIssuesPreview } from '../../../features/integrations'
import { JiraOAuthSetup } from '../../../features/integrations'
import { JiraProjectsPanel } from '../../../features/integrations'
import { GitOAuthSetup as OAuthSetup } from '../../../features/integrations'
import { StatusPill } from './StatusPill'
import { validatePatPayload } from '../validators/settingsValidation'

export type IntegrationCardProps = {
  integration: IntegrationInfo
  busy: boolean
  onOAuth: () => void
  onDisconnect: () => void
  onTest: () => void
  onPatConnected: () => Promise<void>
  onOAuthSaved: () => Promise<void>
  onError: (message: string) => void
}

export const IntegrationCard = ({
  integration,
  busy,
  onOAuth,
  onDisconnect,
  onTest,
  onPatConnected,
  onOAuthSaved,
  onError,
}: IntegrationCardProps) => {
  const connected = integration.status === 'connected'
  const [authMethod, setAuthMethod] = useState<AuthMethod>(integration.id === 'jira' ? 'pat' : 'oauth')
  const [showConnectForm, setShowConnectForm] = useState(false)
  const [token, setToken] = useState('')
  const [email, setEmail] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handlePatSubmit = async (event: FormEvent) => {
    event.preventDefault()

    const validation = validatePatPayload(integration.id, {
      token,
      email: email || undefined,
      baseUrl: baseUrl || undefined,
    })

    if (!validation.isValid) {
      onError(validation.error || 'Verifica los campos ingresados para la conexión con PAT.')
      return
    }

    setSubmitting(true)
    try {
      await api.connectWithPat(integration.id, {
        token: token.trim(),
        email: email ? email.trim() : undefined,
        base_url: baseUrl ? baseUrl.trim() : undefined,
      })
      setShowConnectForm(false)
      setToken('')
      await onPatConnected()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error al conectar mediante PAT')
    } finally {
      setSubmitting(false)
    }
  }

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
            onSaved={() => void onPatConnected()}
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
            onSaved={() => void onPatConnected()}
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
            onSaved={() => void onPatConnected()}
            onError={onError}
          />
        </div>
      ) : null}

      {showConnectForm ? (
        <div className="mt-6 border-t border-[var(--color-border)] pt-5 space-y-4">
          <fieldset className="space-y-3">
            <legend className="text-sm font-bold text-slate-800">Método de Autenticación</legend>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="radio"
                  name={`${integration.id}-auth`}
                  checked={authMethod === 'oauth'}
                  onChange={() => setAuthMethod('oauth')}
                />
                <span className="font-semibold text-slate-800">OAuth 2.0</span>
                {integration.oauth_configured ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                    Configurado
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
                    Requiere configuración
                  </span>
                )}
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="radio"
                  name={`${integration.id}-auth`}
                  checked={authMethod === 'pat'}
                  onChange={() => setAuthMethod('pat')}
                />
                <span className="font-semibold text-slate-800">Personal Access Token (PAT)</span>
              </label>
            </div>
          </fieldset>

          {authMethod === 'oauth' ? (
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
                  defaultRedirect="http://127.0.0.1:8000/api/integrations/github/callback"
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
                  defaultRedirect="http://127.0.0.1:8000/api/integrations/gitlab/callback"
                  showBaseUrl
                  onSaved={onOAuthSaved}
                  onContinueOAuth={onOAuth}
                  onCancel={() => setShowConnectForm(false)}
                />
              ) : null}
            </div>
          ) : (
            <form className="mt-4 space-y-3" onSubmit={(event) => void handlePatSubmit(event)}>
              {integration.id === 'jira' ? (
                <>
                  <p className="text-xs text-[var(--color-ink-muted)]">
                    Recomendado para entornos de desarrollo. Crea tu token en{' '}
                    <a
                      href="https://id.atlassian.com/manage-profile/security/api-tokens"
                      target="_blank"
                      rel="noreferrer"
                      className="text-[#002777] font-semibold underline hover:text-[#004497]"
                    >
                      id.atlassian.com → Security → API tokens
                    </a>
                    .
                  </p>
                  <label className="block text-sm">
                    <span className="mb-1 block text-xs font-semibold text-slate-700">Correo de Atlassian</span>
                    <input
                      required
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="input-field"
                      placeholder="usuario@organizacion.com"
                      aria-label="Correo de Atlassian"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block text-xs font-semibold text-slate-700">
                      URL del Sitio Jira (ejemplo: https://mi-dominio.atlassian.net)
                    </span>
                    <input
                      required
                      type="url"
                      value={baseUrl}
                      onChange={(event) => setBaseUrl(event.target.value)}
                      className="input-field"
                      placeholder="https://empresa.atlassian.net"
                      aria-label="URL del sitio Jira"
                    />
                  </label>
                </>
              ) : null}
              {integration.id === 'gitlab' ? (
                <label className="block text-sm">
                  <span className="mb-1 block text-xs font-semibold text-slate-700">
                    URL de GitLab (opcional — por defecto https://gitlab.com)
                  </span>
                  <input
                    type="url"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://gitlab.com"
                    className="input-field"
                    aria-label="URL de GitLab"
                  />
                </label>
              ) : null}
              <label className="block text-sm">
                <span className="mb-1 block text-xs font-semibold text-slate-700">Personal Access Token (PAT)</span>
                <input
                  required
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  className="input-field font-mono"
                  placeholder="ghp_..., glpat-..., etc."
                  aria-label={`Token de acceso personal de ${integration.name}`}
                />
              </label>
              <div className="flex flex-wrap gap-3 pt-1">
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? 'Conectando…' : 'Guardar conexión'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowConnectForm(false)}
                  className="btn-secondary text-xs py-2 px-4 cursor-pointer"
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>
      ) : null}
    </article>
  )
}
