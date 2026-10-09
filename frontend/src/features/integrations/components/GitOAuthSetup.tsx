import type { FormEvent } from 'react'
import { useEffect, useState } from 'react'
import { CheckCircle2, ExternalLink, Key, Lock, Settings } from 'lucide-react'
import { api } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

type OAuthStatus = {
  configured: boolean
  client_id_set: boolean
  client_secret_set: boolean
  redirect_uri: string
  base_url?: string
}

type OAuthSetupProps = {
  provider: 'github' | 'gitlab'
  title: string
  docsUrl: string
  docsLabel: string
  defaultRedirect: string
  showBaseUrl?: boolean
  defaultBaseUrl?: string
  onSaved: () => void | Promise<void>
  onContinueOAuth?: () => void
  onCancel?: () => void
}

export const OAuthSetup = ({
  provider,
  title,
  docsUrl,
  docsLabel,
  defaultRedirect,
  showBaseUrl = false,
  defaultBaseUrl = 'https://gitlab.com',
  onSaved,
  onContinueOAuth,
  onCancel,
}: OAuthSetupProps) => {
  const { toast } = useToast()
  const [status, setStatus] = useState<OAuthStatus | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [redirectUri, setRedirectUri] = useState(defaultRedirect)
  const [baseUrl, setBaseUrl] = useState(defaultBaseUrl)
  const [busy, setBusy] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const providerLabel = provider === 'github' ? 'GitHub' : 'GitLab'

  const load = async () => {
    try {
      const data =
        provider === 'github'
          ? await api.getGitHubOAuth()
          : await api.getGitLabOAuth()
      setStatus(data)
      setRedirectUri(data.redirect_uri || defaultRedirect)
      if ('base_url' in data && typeof data.base_url === 'string') {
        setBaseUrl(data.base_url)
      }
    } catch {
      // Ignorar error inicial de carga
    }
  }

  useEffect(() => {
    void load()
  }, [provider])

  const saveCredentials = async (): Promise<boolean> => {
    setBusy(true)
    setError(null)
    try {
      if (provider === 'github') {
        await api.saveGitHubOAuth({
          client_id: clientId,
          client_secret: clientSecret || undefined,
          redirect_uri: redirectUri,
        })
      } else {
        await api.saveGitLabOAuth({
          client_id: clientId,
          client_secret: clientSecret || undefined,
          redirect_uri: redirectUri,
          base_url: baseUrl || undefined,
        })
      }
      await load()
      setClientSecret('')
      setIsEditing(false)
      toast.success(`Credenciales OAuth de ${providerLabel} guardadas con éxito.`)
      await onSaved()
      return true
    } catch (err) {
      const msg = err instanceof Error ? err.message : `Error al guardar configuración OAuth de ${providerLabel}`
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

  // Si ya está configurado y el usuario no está editando
  if (status?.configured && !isEditing) {
    return (
      <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <span className="text-xs font-semibold text-slate-900">
              Credenciales OAuth 2.0 registradas para {providerLabel}
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
          {showBaseUrl && status.base_url ? (
            <p>
              <span className="font-medium text-slate-500">URL Instancia: </span>
              <span className="font-mono text-slate-800">{status.base_url}</span>
            </p>
          ) : null}
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
      </div>
    )
  }

  // Formulario de configuración de credenciales OAuth
  return (
    <form
      onSubmit={(event) => void handleSubmit(event, false)}
      className="space-y-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
            <Key className="h-3.5 w-3.5 text-[#002777]" />
            Configuración de Credenciales OAuth 2.0 ({providerLabel})
          </h3>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
            Crea una aplicación OAuth en{' '}
            <a
              href={docsUrl}
              target="_blank"
              rel="noreferrer"
              className="text-[#002777] font-semibold underline hover:text-[#004497] inline-flex items-center gap-0.5"
            >
              {docsLabel}
              <ExternalLink className="h-2.5 w-2.5" />
            </a>{' '}
            e ingresa la URL de callback (Redirect URI) exactamente como se indica abajo.
          </p>
        </div>

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

      {showBaseUrl ? (
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold text-slate-700">
            URL de la Instancia GitLab (opcional — por defecto https://gitlab.com)
          </span>
          <input
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            className="input-field text-xs"
            placeholder="https://gitlab.com"
            aria-label="URL de la Instancia GitLab"
          />
        </label>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold text-slate-700">
            Client ID / Application ID <span className="text-red-500">*</span>
          </span>
          <input
            required
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
            className="input-field text-xs"
            placeholder={status?.client_id_set ? 'Client ID guardado' : 'Ej: Ov23li...'}
            aria-label={`${title} Client ID`}
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold text-slate-700">
            Client Secret <span className="text-red-500">*</span>
          </span>
          <div className="relative">
            <input
              required={!status?.client_secret_set}
              type="password"
              value={clientSecret}
              onChange={(event) => setClientSecret(event.target.value)}
              className="input-field text-xs"
              placeholder={status?.client_secret_set ? '•••• guardado — deja en blanco para mantener' : 'Ej: sec_...'}
              aria-label={`${title} Client Secret`}
            />
            <Lock className="absolute right-3 top-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
          </div>
        </label>
      </div>

      <label className="block text-sm">
        <span className="mb-1 block text-xs font-semibold text-slate-700">
          Redirect URI / URL de Callback (Debe coincidir en {providerLabel}) <span className="text-red-500">*</span>
        </span>
        <input
          required
          value={redirectUri}
          onChange={(event) => setRedirectUri(event.target.value)}
          className="input-field font-mono text-xs text-slate-800"
          aria-label={`${title} Redirect URI`}
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
  )
}

