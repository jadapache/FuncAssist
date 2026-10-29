import { useState } from 'react'
import { CheckCircle2, ExternalLink, Key, RefreshCw, Trash2, X } from 'lucide-react'
import { IntegrationLogo } from './IntegrationLogo'
import { JiraProjectsPanel } from '../../../integrations/components/JiraProjectsPanel'
import { GitHostingReposPanel } from '../../../integrations/components/GitHostingReposPanel'
import type { IntegrationInfo } from '../../../../types'
import { api } from '../../../../api/client'
import { useToast } from '../../../../context/ToastContext'

interface IntegrationConfigModalProps {
  integration: IntegrationInfo | null
  isOpen: boolean
  onClose: () => void
  onRefresh: () => Promise<void>
  onConnectOAuth: (id: string) => Promise<void>
  onConnectPat: (id: string, token: string, email?: string, url?: string) => Promise<void>
  onDisconnect: (id: string) => Promise<void>
}

export const IntegrationConfigModal = ({
  integration,
  isOpen,
  onClose,
  onRefresh,
  onConnectOAuth,
  onConnectPat,
  onDisconnect,
}: IntegrationConfigModalProps) => {
  const { toast } = useToast()
  const [authMode, setAuthMode] = useState<'oauth' | 'pat'>('pat')
  const [token, setToken] = useState('')
  const [email, setEmail] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)

  if (!isOpen || !integration) return null

  const isConnected = integration.status === 'connected'
  const isJira = integration.id === 'jira'
  const isGit = integration.id === 'github' || integration.id === 'gitlab'

  const handleConnectPat = async () => {
    if (!token.trim()) {
      toast.warning('Ingresa el token de acceso personal.')
      return
    }
    setBusy(true)
    try {
      await onConnectPat(integration.id, token.trim(), email.trim() || undefined, url.trim() || undefined)
      setToken('')
      setEmail('')
      setUrl('')
      await onRefresh()
    } finally {
      setBusy(false)
    }
  }

  const handleTest = async () => {
    setBusy(true)
    try {
      const res = await api.testIntegration(integration.id)
      if (res.ok) {
        toast.success(res.message || 'Conexión verificada con éxito.')
      } else {
        toast.error(res.message || 'La verificación de la conexión falló.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al probar conexión.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-200"
    >
      <div className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-50 border border-slate-100 p-2 shadow-2xs">
              <IntegrationLogo id={integration.id} className="h-7 w-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-slate-900">{integration.name}</h3>
                {isConnected ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                    <CheckCircle2 className="h-3 w-3" />
                    <span>Conectado</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                    Desconectado
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                {integration.description || 'Configuración y sincronización con FuncAssist'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 cursor-pointer"
            aria-label="Cerrar modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Info banner when connected */}
        {isConnected ? (
          <div className="rounded-xl border border-blue-200/80 bg-blue-50/60 p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Cuenta vinculada:</span>
              <span className="font-medium text-slate-900">{integration.account_label || 'Activa'}</span>
            </div>
            {integration.workspace_label && (
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700">Espacio de trabajo:</span>
                <span className="font-mono text-slate-800">{integration.workspace_label}</span>
              </div>
            )}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-blue-100">
              <button
                type="button"
                disabled={busy}
                onClick={handleTest}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer shadow-2xs"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
                <span>Probar Conexión</span>
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={async () => {
                  if (window.confirm(`¿Desconectar ${integration.name}?`)) {
                    await onDisconnect(integration.id)
                    await onRefresh()
                  }
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 bg-red-50 text-xs font-semibold text-red-700 hover:bg-red-100 cursor-pointer"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>Desconectar</span>
              </button>
            </div>
          </div>
        ) : (
          /* Connection setup form */
          <div className="space-y-4">
            <div className="flex rounded-xl bg-slate-100 p-1 border border-slate-200/70">
              <button
                type="button"
                onClick={() => setAuthMode('pat')}
                className={`flex-1 rounded-lg py-1.5 text-xs font-bold transition cursor-pointer ${
                  authMode === 'pat' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Personal Access Token (PAT)
              </button>
              <button
                type="button"
                onClick={() => setAuthMode('oauth')}
                className={`flex-1 rounded-lg py-1.5 text-xs font-bold transition cursor-pointer ${
                  authMode === 'oauth' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                OAuth 2.0
              </button>
            </div>

            {authMode === 'oauth' ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-3">
                <p className="text-xs text-slate-600 leading-relaxed">
                  Conéctate directamente autorizando a FuncAssist a través de la interfaz web de {integration.name}.
                </p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onConnectOAuth(integration.id)}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer shadow-xs transition"
                >
                  <ExternalLink className="h-4 w-4" />
                  <span>Conectar con {integration.name} (OAuth)</span>
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Token de Acceso (PAT)</label>
                  <div className="relative mt-1">
                    <Key className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                    <input
                      type="password"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder="Pega aquí tu Personal Access Token..."
                      className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-xs font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>

                {isJira && (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700">Correo Electrónico (Atlassian Account)</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="tu.correo@empresa.com"
                      className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-slate-700">
                    URL Base / Instancia ({isJira ? 'Opcional si usas cloud' : 'Opcional si usas cloud'})
                  </label>
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={isJira ? 'https://tu-organizacion.atlassian.net' : 'https://git.mi-empresa.com'}
                    className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-xs font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <button
                  type="button"
                  disabled={busy || !token.trim()}
                  onClick={handleConnectPat}
                  className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer shadow-xs transition"
                >
                  {busy ? 'Verificando y conectando...' : 'Guardar y Conectar PAT'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Associated panels when connected */}
        {isConnected && isJira && (
          <div className="pt-2 border-t border-slate-100">
            <JiraProjectsPanel onSaved={onRefresh} onError={(err) => toast.error(err)} />
          </div>
        )}

        {isConnected && isGit && (
          <div className="pt-2 border-t border-slate-100">
            <GitHostingReposPanel
              integrationId={integration.id as 'github' | 'gitlab'}
              heading={`Repositorios de ${integration.name}`}
              description="Selecciona los repositorios que FuncAssist sincronizará para consultas y contexto."
              onSaved={onRefresh}
              onError={(msg) => toast.error(msg)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
