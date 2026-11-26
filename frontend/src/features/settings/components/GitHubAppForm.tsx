import type { FormEvent } from 'react'
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../../../api/client'
import { GITHUB_APP_MINIMUM_PERMISSIONS, validateGitHubApp } from '../utils/githubApp'

export type GitHubAppFormProps = {
  onConnected: () => Promise<void>
  onError: (message: string) => void
}

export const GitHubAppForm = ({ onConnected, onError }: GitHubAppFormProps) => {
  const [appId, setAppId] = useState('')
  const [installationId, setInstallationId] = useState('')
  const [privateKey, setPrivateKey] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const result = validateGitHubApp({ appId, privateKey, installationId })
    if (!result.ok) {
      setFormError(result.error)
      return
    }
    setFormError(null)
    setSubmitting(true)
    try {
      await api.connectServiceAccount('github', result.payload)
      await onConnected()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo conectar la GitHub App')
    } finally {
      setPrivateKey('')
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-3">
      <h3 className="text-sm font-bold text-slate-900">Conectar con GitHub App</h3>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Crea una GitHub App con permisos de solo lectura ({GITHUB_APP_MINIMUM_PERMISSIONS.join(', ')})
        e instálala solo en los repositorios necesarios. Cualquier permiso de escritura será
        rechazado.
      </p>
      <label className="block text-xs font-semibold text-slate-600">
        App ID
        <input
          type="text"
          inputMode="numeric"
          value={appId}
          onChange={(event) => setAppId(event.target.value)}
          autoComplete="off"
          required
          className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-mono"
        />
      </label>
      <label className="block text-xs font-semibold text-slate-600">
        Installation ID (opcional)
        <input
          type="text"
          inputMode="numeric"
          value={installationId}
          onChange={(event) => setInstallationId(event.target.value)}
          autoComplete="off"
          className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-mono"
        />
        <span className="mt-1 block font-normal text-[var(--color-ink-muted)]">
          Si se omite, se usa la única instalación de la App.
        </span>
      </label>
      <label className="block text-xs font-semibold text-slate-600">
        Clave privada (PEM)
        <textarea
          value={privateKey}
          onChange={(event) => setPrivateKey(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          required
          rows={6}
          placeholder="-----BEGIN RSA PRIVATE KEY-----"
          className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-mono"
        />
        <span className="mt-1 block font-normal text-[var(--color-ink-muted)]">
          Se guarda cifrada y nunca se muestra de nuevo.
        </span>
      </label>
      {formError ? <p className="text-xs text-[var(--color-bad)]">{formError}</p> : null}
      <button
        type="submit"
        disabled={submitting || !appId.trim() || !privateKey.trim()}
        className="btn-primary text-xs py-2 px-4 disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
      >
        {submitting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : null}
        <span>Conectar</span>
      </button>
    </form>
  )
}
