import type { IntegrationInfo } from '../../../types'
import {
  GITHUB_APP_MINIMUM_PERMISSIONS,
  formatRepositorySelection,
  isReadOnlyLevel,
  parseGitHubAppDetails,
} from '../utils/githubApp'
import { formatConfiguredAt } from '../utils/serviceAccount'

export const GitHubAppStatus = ({ integration }: { integration: IntegrationInfo }) => {
  const details = parseGitHubAppDetails(integration.details)
  const configuredAt = formatConfiguredAt(details.configuredAt)
  const account = details.accountLogin ?? integration.account_label

  return (
    <div className="space-y-1.5">
      {account ? (
        <p>
          <span className="font-semibold text-slate-500">Cuenta / organización instalada: </span>
          <span className="font-medium text-slate-800">{account}</span>
        </p>
      ) : null}
      {details.appId ? (
        <p>
          <span className="font-semibold text-slate-500">GitHub App: </span>
          <span className="font-mono text-slate-800">
            {details.appId}
            {details.installationId ? ` · instalación ${details.installationId}` : ''}
          </span>
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-semibold text-slate-500">Permisos concedidos: </span>
        {details.permissions.length > 0 ? (
          details.permissions.map(({ name, level }) => (
            <span
              key={name}
              className={
                isReadOnlyLevel(level)
                  ? 'rounded-full bg-blue-100 px-2 py-0.5 font-mono text-[10px] font-bold text-blue-800'
                  : 'rounded-full bg-red-100 px-2 py-0.5 font-mono text-[10px] font-bold text-red-800'
              }
            >
              {name}: {level}
            </span>
          ))
        ) : (
          <span className="text-slate-800">Sin datos</span>
        )}
      </div>
      <p>
        <span className="font-semibold text-slate-500">Alcance de la instalación: </span>
        <span
          className={
            details.repositorySelection === 'all'
              ? 'rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-800'
              : 'text-slate-800'
          }
        >
          {formatRepositorySelection(details.repositorySelection)}
        </span>
      </p>
      <p className="text-[var(--color-ink-muted)]">
        Permisos mínimos: {GITHUB_APP_MINIMUM_PERMISSIONS.join(', ')} (solo lectura). Los tokens de
        instalación duran 1 hora y se renuevan solos.
      </p>
      {details.configuredBy ? (
        <p>
          <span className="font-semibold text-slate-500">Configurada por: </span>
          <span className="text-slate-800">
            {details.configuredBy}
            {configuredAt ? ` el ${configuredAt}` : ''}
          </span>
        </p>
      ) : null}
    </div>
  )
}
