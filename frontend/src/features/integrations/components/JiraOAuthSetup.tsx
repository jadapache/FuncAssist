import type { FormEvent } from 'react'
import { useEffect, useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronUp, ExternalLink, HelpCircle, Key, Lock, Settings } from 'lucide-react'
import { api } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

type ScopeGuideItem = {
  scope: string
  label: string
  where: string
  required: boolean
}

type JiraOAuthSetupProps = {
  onSaved: () => void | Promise<void>
  onContinueOAuth?: () => void
  onCancel?: () => void
}

export const JiraOAuthSetup = ({ onSaved, onContinueOAuth, onCancel }: JiraOAuthSetupProps) => {
  const { toast } = useToast()
  const [status, setStatus] = useState<{
    configured: boolean
    client_id_set: boolean
    client_secret_set: boolean
    redirect_uri: string
    scopes?: string[]
    scope_guide?: ScopeGuideItem[]
  } | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [redirectUri, setRedirectUri] = useState('http://127.0.0.1:8000/api/integrations/jira/callback')
  const [busy, setBusy] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showGuide, setShowGuide] = useState(false)

  const load = async () => {
    try {
      const data = await api.getJiraOAuth()
      setStatus(data)
      setRedirectUri(data.redirect_uri)
    } catch {
      // Ignorar error inicial
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const saveCredentials = async (): Promise<boolean> => {
    setBusy(true)
    setError(null)
    try {
      await api.saveJiraOAuth({
        client_id: clientId,
        client_secret: clientSecret || undefined,
        redirect_uri: redirectUri,
      })
      await load()
      setClientSecret('')
      setIsEditing(false)
      toast.success('Configuración OAuth de Jira guardada con éxito.')
      await onSaved()
      return true
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al guardar la configuración OAuth de Jira'
      setError(msg)
      toast.error(msg)
      return false
    } finally {
      setBusy(false)
    }
  }

  const handleSubmit = async (event: FormEvent, andConnect = false) => {
    event.preventDefault()
    const success = await saveCredentials()
    if (success && andConnect && onContinueOAuth) {
      onContinueOAuth()
    }
  }

  const activeScopes = status?.scopes ?? ['read:jira-work', 'offline_access']
  const scopeGuide = status?.scope_guide ?? []

  // Si ya está configurado y el usuario no está editando
  if (status?.configured && !isEditing) {
    return (
      <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <span className="text-xs font-semibold text-slate-900">
              Credenciales OAuth 2.0 registradas para Jira Software
            </span>
          </div>
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="inline-flex items-center gap-1 text-xs text-[#002777] hover:underline font-semibold cursor-pointer"
          >
            <Settings className="h-3.5 w-3.5" />
            <span>Modificar credenciales</span>
          </button>
        </div>

        <div className="text-xs text-slate-600 space-y-1">
          <p>
            <span className="font-medium text-slate-500">Redirect URI / Callback URL: </span>
            <code className="rounded bg-white px-1.5 py-0.5 border border-slate-200 font-mono text-[11px] text-slate-800">
              {status.redirect_uri}
            </code>
          </p>
          <p>
            <span className="font-medium text-slate-500">Permisos activos: </span>
            <span className="font-mono text-[11px] text-slate-700">{activeScopes.join(', ')}</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 pt-1">
          {onContinueOAuth ? (
            <button
              type="button"
              onClick={onContinueOAuth}
              disabled={busy}
              className="btn-primary text-xs py-2 px-4 cursor-pointer"
            >
              Continuar con OAuth
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setShowGuide((prev) => !prev)}
            className="btn-secondary text-xs py-2 px-3 inline-flex items-center gap-1 cursor-pointer"
          >
            <HelpCircle className="h-3.5 w-3.5 text-slate-500" />
            <span>{showGuide ? 'Ocultar guía de permisos' : 'Guía de permisos Atlassian'}</span>
          </button>
          {onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              className="btn-secondary text-xs py-2 px-4 cursor-pointer"
            >
              Cancelar
            </button>
          ) : null}
        </div>

        {/* Guía desplegable de permisos si está activo */}
        {showGuide ? (
          <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-xs space-y-2">
            <h4 className="font-bold text-slate-800">Checklist para Atlassian Developer Console:</h4>
            <ol className="list-decimal space-y-1 pl-4 text-slate-600">
              <li>
                Accede a{' '}
                <a
                  href="https://developer.atlassian.com/console/myapps/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[#002777] font-semibold underline"
                >
                  developer.atlassian.com/console/myapps
                </a>{' '}
                y selecciona tu app OAuth 2.0 (3LO).
              </li>
              <li>
                En <strong>Authorization</strong> → OAuth 2.0 (3LO) → Callback URL: añade{' '}
                <code className="bg-slate-100 px-1 py-0.5 rounded">{status.redirect_uri}</code>.
              </li>
              <li>
                En <strong>Permissions</strong> → añade <em>Jira API</em> (y <em>Jira Software API</em>) y habilita los scopes solicitados.
              </li>
              <li>
                Debes iniciar sesión con la misma cuenta de Atlassian que creó la app.
              </li>
            </ol>
          </div>
        ) : null}
      </div>
    )
  }

  // Formulario de credenciales OAuth de Jira
  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
      {/* Encabezado y toggle de guía */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
            <Key className="h-3.5 w-3.5 text-[#002777]" />
            Configuración de Credenciales OAuth 2.0 (Jira Software)
          </h3>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
            Obtén el Client ID y Client Secret desde la pestaña <strong>Settings</strong> de tu app en{' '}
            <a
              href="https://developer.atlassian.com/console/myapps/"
              target="_blank"
              rel="noreferrer"
              className="text-[#002777] font-semibold underline hover:text-[#004497] inline-flex items-center gap-0.5"
            >
              Atlassian Developer Console
              <ExternalLink className="h-2.5 w-2.5" />
            </a>
            .
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowGuide((val) => !val)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-[#002777] hover:underline cursor-pointer"
          >
            {showGuide ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            <span>{showGuide ? 'Ocultar guía Atlassian' : 'Ver checklist y permisos'}</span>
          </button>
          {status?.configured && isEditing ? (
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="text-xs text-slate-500 hover:text-slate-800 underline cursor-pointer"
            >
              Cancelar edición
            </button>
          ) : null}
        </div>
      </div>

      {/* Guía desplegable de Atlassian */}
      {showGuide ? (
        <div className="rounded-lg border border-slate-200 bg-white p-3.5 text-xs space-y-3">
          <h4 className="font-bold text-slate-800">Checklist para Atlassian Developer Console:</h4>
          <ol className="list-decimal space-y-1.5 pl-4 text-slate-600">
            <li>
              Abre{' '}
              <a
                href="https://developer.atlassian.com/console/myapps/"
                target="_blank"
                rel="noreferrer"
                className="text-[#002777] font-semibold underline"
              >
                developer.atlassian.com/console/myapps
              </a>{' '}
              y selecciona tu aplicación OAuth 2.0.
            </li>
            <li>
              En <strong>Authorization</strong> → OAuth 2.0 (3LO) → define el Callback URL exactamente como:{' '}
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] text-slate-800">{redirectUri}</code>
            </li>
            <li>
              En <strong>Permissions</strong> → añade <em>Jira API</em> (y <em>Jira Software API</em> si necesitas sprints/tableros) y activa los permisos necesarios.
            </li>
            <li>
              Inicia sesión con la misma cuenta Atlassian propietaria de la aplicación en modo desarrollo.
            </li>
          </ol>

          {scopeGuide.length ? (
            <div className="mt-2 overflow-x-auto border-t border-slate-100 pt-2">
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                    <th className="py-1 pr-2">Permiso / Scope</th>
                    <th className="py-1 pr-2">Ubicación en Consola</th>
                    <th className="py-1">Requerido</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {scopeGuide.map((item) => (
                    <tr key={item.scope}>
                      <td className="py-1 pr-2">
                        <code className="font-mono text-slate-800">{item.scope}</code>
                        <div className="text-[10px] text-slate-400">{item.label}</div>
                      </td>
                      <td className="py-1 pr-2 text-slate-500">{item.where}</td>
                      <td className="py-1">
                        {activeScopes.includes(item.scope) ? (
                          <span className="font-semibold text-emerald-600">Sí</span>
                        ) : (
                          <span className="text-slate-400">Opcional</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Formulario de inputs */}
      <form onSubmit={(event) => void handleSubmit(event, false)} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-xs font-semibold text-slate-700">
              Client ID de Jira <span className="text-red-500">*</span>
            </span>
            <input
              required
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
              className="input-field text-xs"
              placeholder={status?.client_id_set ? 'Client ID guardado' : 'Ej: aBcDe12345...'}
              aria-label="Client ID de Jira"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-semibold text-slate-700">
              Client Secret de Jira <span className="text-red-500">*</span>
            </span>
            <div className="relative">
              <input
                required={!status?.client_secret_set}
                type="password"
                value={clientSecret}
                onChange={(event) => setClientSecret(event.target.value)}
                className="input-field text-xs"
                placeholder={status?.client_secret_set ? '•••• guardado — deja en blanco para mantener' : 'Ej: ATOA...'}
                aria-label="Client Secret de Jira"
              />
              <Lock className="absolute right-3 top-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
            </div>
          </label>
        </div>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold text-slate-700">
            Redirect URI (debe coincidir con Atlassian) <span className="text-red-500">*</span>
          </span>
          <input
            required
            value={redirectUri}
            onChange={(event) => setRedirectUri(event.target.value)}
            className="input-field font-mono text-xs text-slate-800"
            aria-label="Redirect URI de Jira"
          />
        </label>

        {error ? <p className="alert-error text-xs">{error}</p> : null}

        <div className="flex flex-wrap items-center gap-2.5 pt-1">
          {onContinueOAuth ? (
            <button
              type="button"
              onClick={(e) => void handleSubmit(e, true)}
              disabled={busy || (!clientId && !status?.client_id_set)}
              className="btn-primary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
            >
              {busy ? 'Guardando…' : 'Guardar y Continuar con OAuth'}
            </button>
          ) : null}

          <button
            type="submit"
            disabled={busy || (!clientId && !status?.client_id_set)}
            className="btn-secondary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
          >
            {busy ? 'Guardando…' : 'Guardar Credenciales'}
          </button>

          {isEditing ? (
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="text-xs text-slate-500 hover:text-slate-700 px-2 py-1 cursor-pointer"
            >
              Cancelar
            </button>
          ) : onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              className="btn-secondary text-xs py-2 px-4 cursor-pointer"
            >
              Cancelar
            </button>
          ) : null}
        </div>
      </form>
    </div>
  )
}

