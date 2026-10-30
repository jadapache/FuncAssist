import { useState } from 'react'
import {
  CheckCircle2,
  ExternalLink,
  Layers,
  Lock,
  Plug,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import type { JiraConnectionStatus } from '../types'
import { JiraOAuthSetup } from '../../integrations/components/JiraOAuthSetup'

export interface JiraIntegrationCardProps {
  status: JiraConnectionStatus | null
  loading: boolean
  onRefresh: () => Promise<void>
  onConnectOAuth: () => Promise<void>
  onConnectPat: (token: string, email?: string, url?: string) => Promise<void>
  onDisconnect: () => Promise<void>
  isAdmin?: boolean
}

export const JiraIntegrationCard = ({
  status,
  loading,
  onRefresh,
  onConnectOAuth,
  onConnectPat,
  onDisconnect,
  isAdmin = false,
}: JiraIntegrationCardProps) => {
  const [authMode, setAuthMode] = useState<'oauth' | 'pat'>('oauth')
  const [patToken, setPatToken] = useState('')
  const [patEmail, setPatEmail] = useState('')
  const [patUrl, setPatUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [isManagingGlobalOAuth, setIsManagingGlobalOAuth] = useState(false)

  const isConnected = Boolean(status?.connected)

  const handleOAuth = async () => {
    setBusy(true)
    try {
      await onConnectOAuth()
    } finally {
      setBusy(false)
    }
  }

  const handlePat = async () => {
    if (!patToken.trim()) return
    setBusy(true)
    try {
      await onConnectPat(patToken.trim(), patEmail.trim() || undefined, patUrl.trim() || undefined)
      setPatToken('')
      setPatEmail('')
      setPatUrl('')
    } finally {
      setBusy(false)
    }
  }

  const handleDisconnect = async () => {
    if (!window.confirm('¿Seguro que deseas desconectar tu cuenta personal de Jira?')) return
    setBusy(true)
    try {
      await onDisconnect()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-[#002777]">
            <Layers className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-slate-900">Jira Software Cloud</h3>
              {isConnected ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span>Conectado</span>
                </span>
              ) : (
                <span className="inline-flex items-center text-[11px] font-medium text-slate-600 bg-slate-100 border border-slate-200 px-2.5 py-0.5 rounded-full">
                  Desconectado
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Conexión personal 3LO vinculada exclusivamente a tu cuenta de usuario.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void onRefresh()}
          disabled={loading || busy}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 cursor-pointer self-start sm:self-auto transition"
          title="Actualizar estado"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Actualizar</span>
        </button>
      </div>

      {isConnected ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 rounded-xl bg-slate-50 p-4 border border-slate-200">
            <div>
              <span className="text-[11px] font-bold text-slate-500 block uppercase tracking-wider">
                Cuenta Conectada
              </span>
              <span className="text-sm font-semibold text-slate-900 break-all">
                {status?.account_email || 'Usuario Atlassian'}
              </span>
            </div>

            <div>
              <span className="text-[11px] font-bold text-slate-500 block uppercase tracking-wider">
                Instancia / Cloud ID
              </span>
              <span className="text-sm font-mono text-slate-700 break-all">
                {status?.cloud_id || status?.site_url || status?.jira_url || 'Instancia por defecto'}
              </span>
            </div>

            {status?.scopes && status.scopes.length > 0 && (
              <div className="sm:col-span-2">
                <span className="text-[11px] font-bold text-slate-500 block uppercase tracking-wider mb-1">
                  Permisos (Scopes) Otorgados
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {status.scopes.map((sc) => (
                    <span
                      key={sc}
                      className="px-2 py-0.5 text-[10px] font-mono font-medium rounded-md bg-white border border-slate-200 text-slate-700"
                    >
                      {sc}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <p className="text-xs text-slate-500">
              Tus credenciales y tokens OAuth se renuevan automáticamente en el backend.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void handleOAuth()}
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 text-xs font-semibold hover:bg-blue-100 transition cursor-pointer"
              >
                <Plug className="h-3.5 w-3.5" />
                <span>Re-autorizar</span>
              </button>
              <button
                type="button"
                onClick={() => void handleDisconnect()}
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 bg-red-50 text-red-700 text-xs font-semibold hover:bg-red-100 transition cursor-pointer"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>Desconectar</span>
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="flex gap-2 border-b border-slate-100 pb-2">
            <button
              type="button"
              onClick={() => setAuthMode('oauth')}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg cursor-pointer transition ${
                authMode === 'oauth'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              OAuth 2.0 (Recomendado)
            </button>
            <button
              type="button"
              onClick={() => setAuthMode('pat')}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg cursor-pointer transition ${
                authMode === 'pat'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              API Token / PAT
            </button>
          </div>

          {authMode === 'oauth' ? (
            <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-5 space-y-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-slate-900">
                  Conexión segura vía Atlassian OAuth 2.0
                </h4>
                <p className="text-xs text-slate-600">
                  Serás redirigido a Atlassian para autorizar a FuncAssist el acceso a tus proyectos e incidencias de Jira.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void handleOAuth()}
                  disabled={busy}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition flex items-center gap-2"
                >
                  <ExternalLink className="h-4 w-4" />
                  <span>{busy ? 'Iniciando...' : 'Conectar con Jira Software'}</span>
                </button>

                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => setIsManagingGlobalOAuth(!isManagingGlobalOAuth)}
                    className="px-3 py-2 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold cursor-pointer transition flex items-center gap-1.5"
                  >
                    <Lock className="h-3.5 w-3.5 text-slate-500" />
                    <span>{isManagingGlobalOAuth ? 'Ocultar credenciales de app' : 'Configurar App Client ID/Secret'}</span>
                  </button>
                )}
              </div>

              {isAdmin && isManagingGlobalOAuth && (
                <div className="pt-3">
                  <JiraOAuthSetup
                    onSaved={async () => {
                      await onRefresh()
                      setIsManagingGlobalOAuth(false)
                    }}
                    onCancel={() => setIsManagingGlobalOAuth(false)}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5 space-y-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-slate-900">
                  Conexión manual con Atlassian API Token
                </h4>
                <p className="text-xs text-slate-500">
                  Ingresa tu token de Atlassian generado en id.atlassian.com/manage-profile/security/api-tokens
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">
                    Correo de Atlassian
                  </label>
                  <input
                    type="email"
                    value={patEmail}
                    onChange={(e) => setPatEmail(e.target.value)}
                    placeholder="usuario@empresa.com"
                    className="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">
                    URL de Jira Cloud (opcional)
                  </label>
                  <input
                    type="url"
                    value={patUrl}
                    onChange={(e) => setPatUrl(e.target.value)}
                    placeholder="https://tuempresa.atlassian.net"
                    className="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="text-xs font-semibold text-slate-700 block mb-1">
                    Atlassian API Token
                  </label>
                  <input
                    type="password"
                    value={patToken}
                    onChange={(e) => setPatToken(e.target.value)}
                    placeholder="ATATT3xFfGF0..."
                    className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>

              <button
                type="button"
                onClick={() => void handlePat()}
                disabled={busy || !patToken.trim()}
                className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition flex items-center gap-1.5"
              >
                <span>{busy ? 'Conectando...' : 'Guardar y conectar con PAT'}</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
