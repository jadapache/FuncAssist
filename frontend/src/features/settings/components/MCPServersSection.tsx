import { useState } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Play,
  Plus,
  RefreshCw,
  Server,
  Terminal,
  Trash2,
  X,
} from 'lucide-react'
import type { McpServerInfo, McpServerPayload } from '../types'

export interface MCPServersSectionProps {
  servers: McpServerInfo[]
  loading: boolean
  onAddServer: (payload: McpServerPayload) => Promise<void>
  onUpdateServer: (id: string, payload: Partial<McpServerPayload & { status?: string }>) => Promise<void>
  onDeleteServer: (id: string) => Promise<void>
  onTestServer: (id: string) => Promise<void>
}

export const MCPServersSection = ({
  servers,
  loading,
  onAddServer,
  onUpdateServer,
  onDeleteServer,
  onTestServer,
}: MCPServersSectionProps) => {
  const [isAdding, setIsAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Form State
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [endpointUrl, setEndpointUrl] = useState('')
  const [transportType, setTransportType] = useState('sse')
  const [authType, setAuthType] = useState('none')
  const [authSecret, setAuthSecret] = useState('')
  const [toolsInput, setToolsInput] = useState('')

  const resetForm = () => {
    setName('')
    setDescription('')
    setEndpointUrl('')
    setTransportType('sse')
    setAuthType('none')
    setAuthSecret('')
    setToolsInput('')
    setIsAdding(false)
    setEditingId(null)
  }

  const handleStartEdit = (server: McpServerInfo) => {
    setEditingId(server.id)
    setName(server.name)
    setDescription(server.description || '')
    setEndpointUrl(server.endpoint_url)
    setTransportType(server.transport_type)
    setAuthType(server.auth_type)
    setAuthSecret('')
    setToolsInput(server.allowed_tools?.join(', ') || '')
    setIsAdding(true)
  }

  const handleSubmit = async () => {
    if (!name.trim() || !endpointUrl.trim()) return

    const allowedTools = toolsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)

    setBusy(true)
    try {
      if (editingId) {
        await onUpdateServer(editingId, {
          name: name.trim(),
          description: description.trim() || undefined,
          endpoint_url: endpointUrl.trim(),
          transport_type: transportType,
          auth_type: authType,
          auth_secret: authSecret.trim() || undefined,
          allowed_tools: allowedTools,
        })
      } else {
        await onAddServer({
          name: name.trim(),
          description: description.trim() || undefined,
          endpoint_url: endpointUrl.trim(),
          transport_type: transportType,
          auth_type: authType,
          auth_secret: authSecret.trim() || undefined,
          allowed_tools: allowedTools,
        })
      }
      resetForm()
    } finally {
      setBusy(false)
    }
  }

  const handleToggleStatus = async (server: McpServerInfo) => {
    const nextStatus = server.status === 'disabled' ? 'configured' : 'disabled'
    setBusy(true)
    try {
      await onUpdateServer(server.id, { status: nextStatus })
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (id: string, serverName: string) => {
    if (!window.confirm(`¿Seguro que deseas eliminar el servidor MCP "${serverName}"?`)) return
    setBusy(true)
    try {
      await onDeleteServer(id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-purple-50 text-purple-700">
            <Server className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-slate-900">
                Model Context Protocol (MCP)
              </h3>
              <span className="inline-flex items-center text-[10px] font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full uppercase tracking-wider">
                Extensible
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Conecta servidores y herramientas externas de contexto (SSE, HTTP) validados contra SSRF.
            </p>
          </div>
        </div>

        {!isAdding && (
          <button
            type="button"
            onClick={() => {
              resetForm()
              setIsAdding(true)
            }}
            disabled={loading || busy}
            className="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold cursor-pointer shadow-xs transition flex items-center gap-1.5 self-start sm:self-auto"
          >
            <Plus className="h-4 w-4" />
            <span>Añadir Servidor MCP</span>
          </button>
        )}
      </div>

      {isAdding && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/30 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Terminal className="h-4 w-4 text-blue-600" />
              <span>{editingId ? 'Editar Servidor MCP' : 'Registrar Nuevo Servidor MCP'}</span>
            </h4>
            <button
              type="button"
              onClick={resetForm}
              className="text-slate-400 hover:text-slate-600 p-1 cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Nombre del Servidor *
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="p. ej. Servidor de Documentación"
                className="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Descripción (opcional)
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Herramientas de búsqueda y lectura de archivos"
                className="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                URL del Endpoint MCP *
              </label>
              <input
                type="url"
                value={endpointUrl}
                onChange={(e) => setEndpointUrl(e.target.value)}
                placeholder="https://mcp-server.empresa.com/sse"
                className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Por seguridad SSRF, el endpoint debe ser HTTPS/HTTP público válido (se bloquean IPs privadas y metadatos cloud).
              </p>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Transporte
              </label>
              <select
                value={transportType}
                onChange={(e) => setTransportType(e.target.value)}
                className="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="sse">Server-Sent Events (SSE)</option>
                <option value="http">HTTP POST / Stream</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Autenticación
              </label>
              <select
                value={authType}
                onChange={(e) => setAuthType(e.target.value)}
                className="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="none">Sin autenticación (Público)</option>
                <option value="bearer">Bearer Token</option>
                <option value="api_key">Header API Key</option>
              </select>
            </div>

            {authType !== 'none' && (
              <div className="sm:col-span-2">
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Secreto / Token de Autenticación
                </label>
                <input
                  type="password"
                  value={authSecret}
                  onChange={(e) => setAuthSecret(e.target.value)}
                  placeholder={editingId ? '•••••••••••••••• (dejar en blanco para mantener)' : 'Secreto'}
                  className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
              </div>
            )}

            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Herramientas Permitidas (Separadas por comas, o * para todas)
              </label>
              <input
                type="text"
                value={toolsInput}
                onChange={(e) => setToolsInput(e.target.value)}
                placeholder="*, search_docs, read_file"
                className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={busy || !name.trim() || !endpointUrl.trim()}
              className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition flex items-center gap-1.5"
            >
              <Check className="h-4 w-4" />
              <span>{busy ? 'Guardando...' : editingId ? 'Actualizar Servidor' : 'Registrar Servidor'}</span>
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="px-3 py-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-medium cursor-pointer transition"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Lista de Servidores */}
      {servers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center space-y-2">
          <div className="flex justify-center text-slate-300">
            <Server className="h-10 w-10 stroke-1" />
          </div>
          <h4 className="text-sm font-semibold text-slate-800">
            No tienes servidores MCP configurados
          </h4>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Puedes conectar servidores externos que cumplan la especificación Model Context Protocol para proporcionar herramientas a los agentes de FuncAssist.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {servers.map((s) => {
            const isConnected = s.status === 'connected'
            const isDisabled = s.status === 'disabled'
            const isError = s.status === 'error'

            return (
              <div
                key={s.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4 transition hover:bg-slate-50"
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold text-slate-900 truncate">
                      {s.name}
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-bold rounded-md bg-white border border-slate-200 text-slate-600 uppercase">
                      {s.transport_type}
                    </span>

                    {isConnected ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                        <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                        <span>Conectado</span>
                      </span>
                    ) : isDisabled ? (
                      <span className="inline-flex items-center text-[11px] font-medium text-slate-500 bg-slate-200 border border-slate-300 px-2.5 py-0.5 rounded-full">
                        Desactivado
                      </span>
                    ) : isError ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-red-50 border border-red-200 px-2.5 py-0.5 rounded-full">
                        <AlertTriangle className="h-3 w-3 text-red-600" />
                        <span>Error</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-0.5 rounded-full">
                        Configurado
                      </span>
                    )}
                  </div>

                  {s.description && (
                    <p className="text-xs text-slate-500">{s.description}</p>
                  )}

                  <div className="flex items-center gap-3 text-xs text-slate-400 font-mono pt-1">
                    <span className="truncate max-w-sm">{s.endpoint_url}</span>
                    {s.allowed_tools && s.allowed_tools.length > 0 && (
                      <span className="text-[11px] text-purple-700 bg-purple-50 px-2 py-0.5 rounded-md font-sans font-medium">
                        {s.allowed_tools.length} herramienta(s)
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => void onTestServer(s.id)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 text-xs font-semibold cursor-pointer transition"
                    title="Probar conectividad del servidor"
                  >
                    <Play className="h-3.5 w-3.5 text-slate-600" />
                    <span>Probar</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => void handleToggleStatus(s)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 text-xs font-semibold cursor-pointer transition"
                  >
                    <span>{isDisabled ? 'Habilitar' : 'Deshabilitar'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleStartEdit(s)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-blue-700 hover:bg-blue-50 text-xs font-semibold cursor-pointer transition"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    <span>Editar</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => void handleDelete(s.id, s.name)}
                    disabled={busy}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                    title="Eliminar servidor"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
