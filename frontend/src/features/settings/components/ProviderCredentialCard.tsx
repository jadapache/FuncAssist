import { useState } from 'react'
import {
  CheckCircle2,
  Key,
  Shield,
  Trash2,
  Play,
  RefreshCw,
  Eye,
  EyeOff,
  AlertTriangle,

} from 'lucide-react'
import type { ProviderCredentialInfo } from '../types'

export interface ProviderCredentialCardProps {
  provider: string
  label: string
  description: string
  credential?: ProviderCredentialInfo
  onSave: (apiKey: string) => Promise<void>
  onTest: () => Promise<void>
  onDelete: () => Promise<void>
}

export const ProviderCredentialCard = ({
  label,
  description,
  credential,
  onSave,
  onTest,
  onDelete,
}: ProviderCredentialCardProps) => {
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  const isConfigured = Boolean(
    credential?.is_configured ?? credential?.configured ?? (credential?.status && credential.status !== 'unconfigured')
  )
  const isValid = credential?.is_valid ?? (credential?.status === 'active')
  const hasError = Boolean(credential?.validation_error || credential?.status === 'validation_failed' || credential?.status === 'error')

  const handleSave = async () => {
    if (!apiKeyInput.trim()) return
    setBusy(true)
    try {
      await onSave(apiKeyInput.trim())
      setApiKeyInput('')
      setIsEditing(false)
    } finally {
      setBusy(false)
    }
  }

  const handleTest = async () => {
    setBusy(true)
    try {
      await onTest()
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(`¿Seguro que deseas eliminar la API Key de ${label}?`)) return
    setBusy(true)
    try {
      await onDelete()
      setApiKeyInput('')
      setIsEditing(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs transition hover:border-slate-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-[#002777]">
            <Key className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-900">{label}</h4>
            <p className="text-xs text-slate-500">{description}</p>
          </div>
        </div>

        <div>
          {isConfigured ? (
            hasError ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-700">
                <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                <span>Error de validación</span>
              </span>
            ) : isValid ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                <span>Configurada y Activa</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-200 px-2.5 py-1 text-xs font-semibold text-blue-700">
                <Shield className="h-3.5 w-3.5 text-blue-600" />
                <span>Configurada</span>
              </span>
            )
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600">
              Pendiente de configurar
            </span>
          )}
        </div>
      </div>

      {credential?.validation_error ? (
        <div className="mb-3 rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-800">
          {credential.validation_error}
        </div>
      ) : null}

      {isEditing || !isConfigured ? (
        <div className="space-y-3 pt-2">
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder={isConfigured ? '•••••••••••••••• (Introduce nueva clave)' : 'Pega tu API Key personal aquí'}
              className="w-full px-3 py-2 pr-10 text-xs font-mono text-slate-900 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              autoFocus={isEditing}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleSave()
              }}
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1 cursor-pointer"
              title={showKey ? 'Ocultar' : 'Mostrar'}
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={busy || !apiKeyInput.trim()}
              className="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition"
            >
              {busy ? 'Guardando...' : isConfigured ? 'Actualizar clave' : 'Guardar clave'}
            </button>
            {isConfigured && (
              <button
                type="button"
                onClick={() => {
                  setApiKeyInput('')
                  setIsEditing(false)
                }}
                className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-medium cursor-pointer transition"
              >
                Cancelar
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="text-xs text-slate-500 font-mono">
            Clave guardada y cifrada en AES-256.
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleTest()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold cursor-pointer transition"
              title="Probar credencial"
            >
              <Play className="h-3.5 w-3.5 text-slate-600" />
              <span>{busy ? 'Validando...' : 'Probar'}</span>
            </button>
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold cursor-pointer transition"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Reemplazar</span>
            </button>
            <button
              type="button"
              onClick={() => void handleDelete()}
              disabled={busy}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
              title="Eliminar credencial"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
