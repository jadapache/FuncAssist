import type { FormEvent } from 'react'
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../../../api/client'
import { validateBaseUrl } from '../utils/serviceAccount'

export type ServiceAccountFormProps = {
  onConnected: () => Promise<void>
  onError: (message: string) => void
}

export const ServiceAccountForm = ({ onConnected, onError }: ServiceAccountFormProps) => {
  const [token, setToken] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const url = validateBaseUrl(baseUrl)
    if (!url.ok) {
      setUrlError(url.error)
      return
    }
    setUrlError(null)
    setSubmitting(true)
    try {
      await api.connectServiceAccount('gitlab', { token: token.trim(), base_url: url.baseUrl })
      await onConnected()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo conectar la cuenta de servicio')
    } finally {
      setToken('')
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-3">
      <h3 className="text-sm font-bold text-slate-900">Conectar con cuenta de servicio</h3>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Crea un token de acceso de proyecto o grupo (o una cuenta de servicio) con rol Reporter y
        solo los permisos <code>read_api</code> (obligatorio), <code>read_repository</code> y{' '}
        <code>read_user</code>. Cualquier permiso de escritura será rechazado.
      </p>
      <label className="block text-xs font-semibold text-slate-600">
        Token de acceso
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          autoComplete="off"
          required
          className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-mono"
        />
      </label>
      <label className="block text-xs font-semibold text-slate-600">
        URL de GitLab (opcional)
        <input
          type="url"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          placeholder="https://gitlab.com"
          className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
        />
        <span className="mt-1 block font-normal text-[var(--color-ink-muted)]">
          Debe usar https.
        </span>
      </label>
      {urlError ? <p className="text-xs text-[var(--color-bad)]">{urlError}</p> : null}
      <button
        type="submit"
        disabled={submitting || !token.trim()}
        className="btn-primary text-xs py-2 px-4 disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
      >
        {submitting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : null}
        <span>Conectar</span>
      </button>
    </form>
  )
}
