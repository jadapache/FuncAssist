import React, { useState } from 'react'
import {
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
  Globe,
  Network,
  Play,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  Wrench,
} from 'lucide-react'
import { useToast } from '../../../context/ToastContext'
import { useMcpManager } from '../hooks/useMcpManager'
import type { MCPTool } from '../types'

export const McpIntegrationPanel: React.FC = () => {
  const { toast } = useToast()
  const {
    info,
    servers,
    loading,
    actionLoading,
    refresh,
    addServer,
    toggleServer,
    removeServer,
    pingServer,
    testTool,
  } = useMcpManager()

  const [activeSubTab, setActiveSubTab] = useState<'server' | 'client'>('server')
  const [selectedSnippetTab, setSelectedSnippetTab] = useState<'claude' | 'cursor' | 'antigravity'>('claude')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  // Add Server Form State
  const [showAddModal, setShowAddModal] = useState(false)
  const [newServerName, setNewServerName] = useState('')
  const [newServerUrl, setNewServerUrl] = useState('')
  const [newServerTransport, setNewServerTransport] = useState<'sse' | 'http'>('sse')
  const [newServerAuthHeader, setNewServerAuthHeader] = useState('')

  // Expandable tools list
  const [expandedServerId, setExpandedServerId] = useState<string | null>(null)

  // Test tool modal
  const [testingTool, setTestingTool] = useState<{ serverId: string; tool: MCPTool } | null>(null)
  const [testToolArgs, setTestToolArgs] = useState('{}')
  const [testToolResult, setTestToolResult] = useState<string | null>(null)

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    toast.success('Copiado al portapapeles', 'Copia exitosa')
    setTimeout(() => setCopiedKey(null), 2000)
  }

  const handleAddServerSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newServerName.trim() || !newServerUrl.trim()) return

    const headers: Record<string, string> = {}
    if (newServerAuthHeader.trim()) {
      headers['Authorization'] = newServerAuthHeader.trim()
    }

    try {
      await addServer({
        name: newServerName.trim(),
        url: newServerUrl.trim(),
        transport: newServerTransport,
        headers,
        enabled: true,
      })
      setShowAddModal(false)
      setNewServerName('')
      setNewServerUrl('')
      setNewServerAuthHeader('')
    } catch {
      // Error is handled in hook
    }
  }

  const handleExecuteTestTool = async () => {
    if (!testingTool) return
    try {
      let parsedArgs: Record<string, any> = {}
      if (testToolArgs.trim()) {
        parsedArgs = JSON.parse(testToolArgs)
      }
      const res = await testTool(testingTool.serverId, testingTool.tool.name, parsedArgs)
      setTestToolResult(typeof res === 'object' ? JSON.stringify(res, null, 2) : String(res))
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error ejecutando herramienta'
      setTestToolResult(`Error: ${msg}`)
    }
  }

  const hostOrigin = window.location.origin
  const sseEndpoint = `${hostOrigin}/api/mcp/sse`
  const directEndpoint = `${hostOrigin}/api/mcp`

  const claudeSnippet = JSON.stringify(
    {
      mcpServers: {
        funcassist: {
          url: sseEndpoint,
          transport: 'sse',
        },
      },
    },
    null,
    2,
  )

  const cursorSnippet = JSON.stringify(
    {
      mcpServers: {
        funcassist: {
          url: sseEndpoint,
        },
      },
    },
    null,
    2,
  )

  const antigravitySnippet = JSON.stringify(
    {
      mcp_servers: [
        {
          name: 'funcassist',
          endpoint: directEndpoint,
          transport: 'http',
        },
      ],
    },
    null,
    2,
  )

  return (
    <div className="space-y-6">
      {/* Header Container */}
      <div className="rounded-2xl border border-[var(--color-border)] bg-white p-6 md:p-8 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--color-border)] pb-6">
          <div className="flex items-start gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-md shadow-[#002777]/20">
              <Network className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-bold tracking-tight text-slate-900">
                  Model Context Protocol (MCP)
                </h1>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 animate-pulse" />
                  MCP v2024-11-05
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
                Arquitectura bidireccional para modelos agénticos: Conecta FuncAssist como servidor para modelos externos (Claude, Cursor, Antigravity) o como cliente para consumir herramientas externas (Jira, GitHub, APIs).
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading}
              className="flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Sincronizar</span>
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="mt-6 flex border-b border-slate-200">
          <button
            type="button"
            onClick={() => setActiveSubTab('server')}
            className={`flex items-center gap-2 border-b-2 py-3 px-4 text-xs font-bold transition-all cursor-pointer ${
              activeSubTab === 'server'
                ? 'border-[#002777] text-[#002777]'
                : 'border-transparent text-slate-500 hover:text-slate-900'
            }`}
          >
            <Server className="h-4 w-4" />
            <span>Servidor MCP FuncAssist</span>
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] text-[#002777]">
              {info?.toolsCount ?? 5} herramientas
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('client')}
            className={`flex items-center gap-2 border-b-2 py-3 px-4 text-xs font-bold transition-all cursor-pointer ${
              activeSubTab === 'client'
                ? 'border-[#002777] text-[#002777]'
                : 'border-transparent text-slate-500 hover:text-slate-900'
            }`}
          >
            <Bot className="h-4 w-4" />
            <span>Servidores MCP Externos (Cliente)</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
              {servers.length} conectados
            </span>
          </button>
        </div>

        {/* ========================================================================= */}
        {/* SUBTAB 1: SERVIDOR MCP FUNCASSIST (Inbound) */}
        {/* ========================================================================= */}
        {activeSubTab === 'server' && (
          <div className="mt-6 space-y-6 animate-in fade-in">
            {/* Endpoints Card */}
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5 space-y-4">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-2">
                <Globe className="h-4 w-4 text-[#002777]" />
                Endpoints Públicos del Protocolo
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-semibold text-slate-800">SSE Handshake (Recomendado)</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(sseEndpoint, 'sse')}
                      className="text-[11px] font-medium text-[#002777] hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      {copiedKey === 'sse' ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
                      <span>{copiedKey === 'sse' ? 'Copiado' : 'Copiar URL'}</span>
                    </button>
                  </div>
                  <code className="block rounded-lg bg-slate-100 p-2 text-[11px] font-mono text-slate-700 truncate">
                    {sseEndpoint}
                  </code>
                  <p className="text-[10px] text-slate-500 mt-1.5">
                    Utilizado por Claude Desktop, Cursor y clientes estándar basados en Server-Sent Events.
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-semibold text-slate-800">JSON-RPC 2.0 Directo</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(directEndpoint, 'direct')}
                      className="text-[11px] font-medium text-[#002777] hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      {copiedKey === 'direct' ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
                      <span>{copiedKey === 'direct' ? 'Copiado' : 'Copiar URL'}</span>
                    </button>
                  </div>
                  <code className="block rounded-lg bg-slate-100 p-2 text-[11px] font-mono text-slate-700 truncate">
                    {directEndpoint}
                  </code>
                  <p className="text-[10px] text-slate-500 mt-1.5">
                    Punto de enlace HTTP POST directo para invocar métodos JSON-RPC individuales.
                  </p>
                </div>
              </div>
            </div>

            {/* Quick Setup Snippets */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <Code2 className="h-4 w-4 text-[#002777]" />
                    Configuración de Conexión en Clientes Externos
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Pega esta configuración en tu archivo de configuración MCP para habilitar las herramientas de FuncAssist.
                  </p>
                </div>

                {/* Snippet Switcher */}
                <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 border border-slate-200">
                  <button
                    type="button"
                    onClick={() => setSelectedSnippetTab('claude')}
                    className={`rounded-lg py-1 px-3 text-xs font-semibold transition cursor-pointer ${
                      selectedSnippetTab === 'claude'
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Claude Desktop
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedSnippetTab('cursor')}
                    className={`rounded-lg py-1 px-3 text-xs font-semibold transition cursor-pointer ${
                      selectedSnippetTab === 'cursor'
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Cursor IDE
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedSnippetTab('antigravity')}
                    className={`rounded-lg py-1 px-3 text-xs font-semibold transition cursor-pointer ${
                      selectedSnippetTab === 'antigravity'
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Antigravity / JSON
                  </button>
                </div>
              </div>

              {/* Snippet Code Viewer */}
              <div className="relative rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs font-mono text-slate-200 shadow-inner">
                <button
                  type="button"
                  onClick={() => {
                    const snippet =
                      selectedSnippetTab === 'claude'
                        ? claudeSnippet
                        : selectedSnippetTab === 'cursor'
                        ? cursorSnippet
                        : antigravitySnippet
                    copyToClipboard(snippet, 'snippet')
                  }}
                  className="absolute top-3 right-3 flex items-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-[11px] font-sans font-medium text-slate-200 transition cursor-pointer"
                >
                  {copiedKey === 'snippet' ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                  <span>{copiedKey === 'snippet' ? 'Copiado' : 'Copiar Configuración'}</span>
                </button>
                <pre className="overflow-x-auto text-[11px] leading-relaxed">
                  {selectedSnippetTab === 'claude' && claudeSnippet}
                  {selectedSnippetTab === 'cursor' && cursorSnippet}
                  {selectedSnippetTab === 'antigravity' && antigravitySnippet}
                </pre>
              </div>
            </div>

            {/* Exposed Tools Grid */}
            <div className="space-y-3">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Wrench className="h-4 w-4 text-[#002777]" />
                Herramientas Expuestas a Modelos Agénticos ({info?.toolsCount ?? 5})
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {(info?.tools ?? []).map((tool) => (
                  <div
                    key={tool.name}
                    className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-blue-200 hover:shadow-md transition"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-mono text-xs font-bold text-[#002777]">
                          {tool.name}
                        </span>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                          tool
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 leading-normal">
                        {tool.description}
                      </p>
                    </div>

                    <div className="mt-3 border-t border-slate-100 pt-2 flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                      <span>Parámetros:</span>
                      <span className="text-slate-700 font-semibold truncate">
                        {Object.keys(tool.inputSchema?.properties ?? {}).join(', ') || 'ninguno'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* SUBTAB 2: SERVIDORES MCP EXTERNOS (Outbound Client) */}
        {/* ========================================================================= */}
        {activeSubTab === 'client' && (
          <div className="mt-6 space-y-6 animate-in fade-in">
            {/* Action Bar */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-slate-900">
                  Conexiones a Servidores MCP Externos
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Permite a los modelos agénticos locales descubrir e invocar herramientas expuestas por servidores remotos.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-1.5 rounded-xl bg-[#002777] hover:bg-[#001f5c] text-white px-3.5 py-2 text-xs font-bold shadow-md transition cursor-pointer"
              >
                <Plus className="h-4 w-4" />
                <span>Agregar Servidor MCP</span>
              </button>
            </div>

            {/* Servers List */}
            {servers.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 p-8 text-center text-xs text-slate-500 space-y-2">
                <Network className="h-8 w-8 mx-auto text-slate-400" />
                <p className="font-semibold text-slate-700 text-sm">
                  No hay servidores MCP externos configurados
                </p>
                <p className="text-slate-500 max-w-md mx-auto">
                  Agrega un servidor MCP (por ejemplo, Jira, GitHub, Base de Datos o API interna) para que los agentes puedan utilizar sus herramientas automáticamente.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {servers.map((server) => {
                  const isExpanded = expandedServerId === server.id
                  const toolsCount = server.cached_tools?.length ?? 0
                  const isPingLoading = actionLoading === `ping-${server.id}`

                  return (
                    <div
                      key={server.id}
                      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-300 transition"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <div
                            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white ${
                              server.enabled ? 'bg-blue-600' : 'bg-slate-400'
                            }`}
                          >
                            <Server className="h-5 w-5" />
                          </div>

                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="font-bold text-slate-900 text-sm">{server.name}</h3>
                              <span
                                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                                  server.enabled
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : 'bg-slate-100 text-slate-600'
                                }`}
                              >
                                {server.enabled ? 'Activo' : 'Inactivo'}
                              </span>
                              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-mono text-slate-600 uppercase">
                                {server.transport}
                              </span>
                            </div>

                            <code className="mt-1 block text-xs font-mono text-slate-500 truncate max-w-md">
                              {server.url}
                            </code>

                            <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
                              <span className="flex items-center gap-1 font-semibold text-slate-700">
                                <Wrench className="h-3 w-3 text-blue-600" />
                                {toolsCount} herramienta(s) descubierta(s)
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void pingServer(server.id)}
                            disabled={isPingLoading}
                            title="Probar conexión y sincronizar herramientas"
                            className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer disabled:opacity-50"
                          >
                            <RefreshCw className={`h-3 w-3 ${isPingLoading ? 'animate-spin text-blue-600' : ''}`} />
                            <span>Sincronizar</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => void toggleServer(server)}
                            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer"
                          >
                            {server.enabled ? 'Deshabilitar' : 'Habilitar'}
                          </button>

                          <button
                            type="button"
                            onClick={() => void removeServer(server.id, server.name)}
                            title="Eliminar servidor"
                            className="p-1.5 text-slate-400 hover:text-red-600 transition cursor-pointer"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>

                          {toolsCount > 0 && (
                            <button
                              type="button"
                              onClick={() => setExpandedServerId(isExpanded ? null : server.id)}
                              className="p-1 text-slate-500 hover:text-slate-800 transition cursor-pointer ml-1"
                            >
                              {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Expandable Tools List */}
                      {isExpanded && server.cached_tools && server.cached_tools.length > 0 && (
                        <div className="mt-4 border-t border-slate-100 pt-3 space-y-2 animate-in fade-in">
                          <span className="text-[11px] font-bold uppercase text-slate-500 tracking-wider">
                            Herramientas Disponibles:
                          </span>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {server.cached_tools.map((t) => (
                              <div
                                key={t.name}
                                className="flex items-start justify-between gap-2 rounded-xl border border-slate-100 bg-slate-50 p-2.5 text-xs"
                              >
                                <div>
                                  <span className="font-mono font-bold text-slate-800 block text-[11px]">
                                    {t.name}
                                  </span>
                                  <p className="text-[11px] text-slate-600 line-clamp-2 mt-0.5">
                                    {t.description}
                                  </p>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setTestingTool({ serverId: server.id, tool: t })
                                    setTestToolArgs('{}')
                                    setTestToolResult(null)
                                  }}
                                  className="shrink-0 flex items-center gap-1 rounded-md bg-white border border-slate-200 px-2 py-1 text-[10px] font-semibold text-blue-700 hover:bg-blue-50 transition cursor-pointer"
                                >
                                  <Play className="h-2.5 w-2.5" />
                                  <span>Probar</span>
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal: Add MCP Server */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Network className="h-5 w-5 text-[#002777]" />
                Registrar Nuevo Servidor MCP
              </h2>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddServerSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Nombre del Servidor <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newServerName}
                  onChange={(e) => setNewServerName(e.target.value)}
                  placeholder="ej. Servidor Jira / GitHub Tools"
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-1 focus:ring-[#002777]"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-800 mb-1">
                    URL del Servidor <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="url"
                    required
                    value={newServerUrl}
                    onChange={(e) => setNewServerUrl(e.target.value)}
                    placeholder="https://mi-mcp-server.com/sse"
                    className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-1 focus:ring-[#002777]"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-800 mb-1">
                    Transporte
                  </label>
                  <select
                    value={newServerTransport}
                    onChange={(e) => setNewServerTransport(e.target.value as 'sse' | 'http')}
                    className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-1 focus:ring-[#002777]"
                  >
                    <option value="sse">SSE</option>
                    <option value="http">HTTP Direct</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Encabezado de Autorización (Opcional)
                </label>
                <input
                  type="text"
                  value={newServerAuthHeader}
                  onChange={(e) => setNewServerAuthHeader(e.target.value)}
                  placeholder="Bearer token_secreto_aqui..."
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-1 focus:ring-[#002777]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={actionLoading === 'create'}
                  className="rounded-xl bg-[#002777] hover:bg-[#001f5c] text-white px-4 py-2 text-xs font-bold shadow-md transition cursor-pointer disabled:opacity-50"
                >
                  {actionLoading === 'create' ? 'Conectando...' : 'Guardar y Sincronizar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Test Tool Invocator */}
      {testingTool && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Play className="h-4 w-4 text-emerald-600" />
                  Ejecutar Herramienta MCP: {testingTool.tool.name}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">{testingTool.tool.description}</p>
              </div>
              <button
                type="button"
                onClick={() => setTestingTool(null)}
                className="text-slate-400 hover:text-slate-600 text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Argumentos JSON (inputSchema):
              </label>
              <textarea
                rows={4}
                value={testToolArgs}
                onChange={(e) => setTestToolArgs(e.target.value)}
                className="w-full rounded-xl border border-slate-300 p-2.5 text-xs font-mono text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-1 focus:ring-[#002777]"
              />
            </div>

            {testToolResult && (
              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Respuesta del Servidor:
                </label>
                <pre className="max-h-48 overflow-y-auto rounded-xl bg-slate-900 p-3 text-[11px] font-mono text-emerald-400">
                  {testToolResult}
                </pre>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setTestingTool(null)}
                className="rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
              >
                Cerrar
              </button>
              <button
                type="button"
                onClick={() => void handleExecuteTestTool()}
                className="rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 text-xs font-bold shadow-md transition cursor-pointer"
              >
                Ejecutar Herramienta
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
