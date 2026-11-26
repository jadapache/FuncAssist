import type { IntegrationInfo } from '../../../types'
import {
  formatConfiguredAt,
  formatExpiry,
  parseServiceAccountDetails,
  type ExpiryDisplay,
} from '../utils/serviceAccount'

const TONE_CLASSES: Record<ExpiryDisplay['tone'], string> = {
  neutral: 'text-slate-800',
  warning: 'rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-800',
  danger: 'rounded-full bg-red-100 px-2 py-0.5 font-semibold text-red-800',
}

export const ServiceAccountStatus = ({ integration }: { integration: IntegrationInfo }) => {
  const details = parseServiceAccountDetails(integration.details)
  const expiry = formatExpiry(details.expiry, details.expiresAt)
  const configuredAt = formatConfiguredAt(details.configuredAt)

  return (
    <div className="space-y-1.5">
      {integration.account_label ? (
        <p>
          <span className="font-semibold text-slate-500">Cuenta (bot): </span>
          <span className="font-medium text-slate-800">{integration.account_label}</span>
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-semibold text-slate-500">Permisos concedidos: </span>
        {details.scopes.length > 0 ? (
          details.scopes.map((scope) => (
            <span
              key={scope}
              className="rounded-full bg-blue-100 px-2 py-0.5 font-mono text-[10px] font-bold text-blue-800"
            >
              {scope}
            </span>
          ))
        ) : (
          <span className="text-slate-800">Sin datos</span>
        )}
      </div>
      <p>
        <span className="font-semibold text-slate-500">Caducidad: </span>
        <span className={TONE_CLASSES[expiry.tone]}>{expiry.label}</span>
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
