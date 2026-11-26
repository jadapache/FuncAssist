import { useState } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Lock,
  Play,
  Plus,
  RefreshCw,
  Server,
  Terminal,
  Trash2,
  X,
} from 'lucide-react'
import type {
  McpAdminServer,
  McpServerCreatePayload,
  McpServerInfo,
  McpServerUpdatePayload,
  McpToolApprovalInput,
} from '../types'
import { MCPToolApprovalPanel } from './MCPToolApprovalPanel'

export interface MCPServersSectionProps {
  isAdmin: boolean
  servers: McpServerInfo[]
  adminServers: McpAdminServer[]
  loading: boolean
  onAddServer: (payload: McpServerCreatePayload) => Promise<boolean>
  onUpdateServer: (id: string, payload: McpServerUpdatePayload) => Promise<boolean>
  onDeleteServer: (id: string) => Promise<void>
  onTestServer: (id: string) => Promise<void>
  onSetTools: (id: string, tools: McpToolApprovalInput[]) => Promise<boolean>
}

const StatusBadge = ({ status }: { status: string }) => {
  if (status === 'connected') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
        <CheckCircle2 className="h-3 w-3 text-emerald-600" />
        <span>Conectado</span>
      </span>
    )
  }
  if (status === 'disabled') {
    return (
      <span className="inline-flex items-center text-[11px] font-medium text-slate-500 bg-slate-200 border border-slate-300 px-2.5 py-0.5 rounded-full">
        Desactivado
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-red-50 border border-red-200 px-2.5 py-0.5 rounded-full">
        <AlertTriangle className="h-3 w-3 text-red-600" />
        <span>Error</span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-0.5 rounded-full">
      Configurado
    </span>
  )
}

const EmptyState = ({ title, text }: { title: string; text: string }) => (
  <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center space-y-2">
    <div className="flex justify-center text-slate-300">
      <Server className="h-10 w-10 stroke-1" />
    </div>
    <h4 className="text-sm font-semibold text-slate-800">{title}</h4>
    <p className="text-xs text-slate-500 max-w-md mx-auto">{text}</p>
  </div>
)

const UserServerList = ({ servers }: { servers: McpServerInfo[] }) => {
  if (servers.length === 0) {
    return (
      <EmptyState
        title="No hay servidores MCP disponibles"
        text="Cuando un administrador registre servidores y apruebe sus herramientas, aparecerán aquí."
      />
    )
  }

  return (
    <div className="space-y-3">
      {servers.map((s) => (
        <div key={s.id} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-slate-900 truncate">{s.name}</span>
            <StatusBadge status={s.status} />
          </div>
          {s.description && <p className="text-xs text-slate-500">{s.description}</p>}
          {s.tools.length === 0 ? (
            <p className="text-xs text-slate-400">Sin herramientas aprobadas.</p>
          ) : (
            <div className="flex flex-wrap gap-2 pt-1">
              {s.tools.map((tool) => (
                <span
                  key={tool.name}
                  className="inline-flex items-center gap-1.5 text-[11px] bg-white border border-slate-200 px-2 py-0.5 rounded-md"
                >
                  <span className="font-mono font-semibold text-slate-800">{tool.name}</span>
                  <span className={tool.read_only ? 'text-emerald-700' : 'text-amber-700'}>
                    {tool.read_only ? 'Solo lectura' : 'Requiere confirmación'}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export const MCPServersSection = ({
  isAdmin,
  servers,
  adminServers,
  loading,
  onAddServer,
  onUpdateServer,
  onDeleteServer,
  onTestServer,
  onSetTools,
}: MCPServersSectionProps) => {
  const [isAdding, setIsAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Form State
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [endpointUrl, setEndpointUrl] = useState('')
  const [transportType, setTransportType] = useState('sse')
  const [authType, setAuthType] = useState('none')

  const editingServer = adminServers.find((s) => s.id === editingId) ?? null

  const resetForm = () => {
    setName('')
    setDescription('')
    setEndpointUrl('')
    setTransportType('sse')
    setAuthType('none')
    setIsAdding(false)
    setEditingId(null)
  }

  const handleStartEdit = (server: McpAdminServer) => {
    setEditingId(server.id)
    setName(server.name)
    setDescription(server.description || '')
    setEndpointUrl(server.endpoint_url)
    setTransportType(server.transport_type)
    setAuthType(server.auth_type)
    setIsAdding(true)
  }

  const handleSubmit = async () => {
    if (!name.trim() || !endpointUrl.trim()) return

    const payload: McpServerCreatePayload = {
      name: name.trim(),
      description: description.trim() || undefined,
      endpoint_url: endpointUrl.trim(),
      transport_type: transportType,
      auth_type: authType,
    }

    if (
      editingServer &&
      payload.endpoint_url !== editingServer.endpoint_url &&
      !window.confirm(
        'Cambiar el endpoint elimina todas las aprobaciones de herramientas de este servidor y habrá que aprobarlas de nuevo. ¿Continuar?',
      )
    ) {
      return
    }

    setBusy(true)
    try {
      const saved = editingId
        ? await onUpdateServer(editingId, payload)
        : await onAddServer(payload)
      if (saved) resetForm()
    } finally {
      setBusy(false)
    }
  }

  const handleToggleStatus = async (server: McpAdminServer) => {
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

  const handleSetTools = async (id: string, tools: McpToolApprovalInput[]) => {
    setBusy(true)
    try {
      return await onSetTools(id, tools)
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
              {isAdmin
                ? 'Registra servidores externos de contexto (SSE, HTTP) y aprueba las herramientas que pueden usar los agentes.'
                : 'Servidores y herramientas externas aprobadas que pueden usar los agentes de FuncAssist.'}
            </p>
          </div>
        </div>

        {isAdmin && !isAdding && (
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

      {!isAdmin && (
        <>
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Lock className="h-3.5 w-3.5 shrink-0" />
            <span>Solo un administrador puede registrar servidores y aprobar herramientas.</span>
          </p>
          <UserServerList servers={servers} />
        </>
      )}

      {isAdmin && isAdding && (
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
                {editingId && ' Cambiar el endpoint elimina todas las aprobaciones de herramientas del servidor.'}
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
          </div>

          <p className="text-[11px] text-slate-500">
            El servidor se registra sin ninguna herramienta aprobada; apruébalas desde el panel de herramientas del servidor.
          </p>

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

      {isAdmin && (adminServers.length === 0 ? (
        <EmptyState
          title="No hay servidores MCP registrados"
          text="Registra servidores que cumplan la especificación Model Context Protocol y aprueba sus herramientas para ponerlas a disposición de los agentes de FuncAssist."
        />
      ) : (
        <div className="space-y-3">
          {adminServers.map((s) => {
            const isDisabled = s.status === 'disabled'
            const isExpanded = expandedId === s.id
            const approvedCount = s.tools.filter((tool) => tool.approved).length

            return (
              <div key={s.id} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1.5 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-slate-900 truncate">
                        {s.name}
                      </span>
                      <span className="px-2 py-0.5 text-[10px] font-bold rounded-md bg-white border border-slate-200 text-slate-600 uppercase">
                        {s.transport_type}
                      </span>
                      <StatusBadge status={s.status} />
                    </div>

                    {s.description && (
                      <p className="text-xs text-slate-500">{s.description}</p>
                    )}

                    <div className="flex items-center gap-3 text-xs text-slate-400 font-mono pt-1">
                      <span className="truncate max-w-sm">{s.endpoint_url}</span>
                      <span className="text-[11px] text-purple-700 bg-purple-50 px-2 py-0.5 rounded-md font-sans font-medium">
                        {approvedCount} herramienta(s) aprobada(s)
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 flex-wrap">
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : s.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-purple-700 hover:bg-purple-50 text-xs font-semibold cursor-pointer transition"
                    >
                      {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                      <span>Herramientas</span>
                    </button>

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

                {isExpanded && (
                  <MCPToolApprovalPanel server={s} disabled={busy} onSetTools={handleSetTools} />
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
