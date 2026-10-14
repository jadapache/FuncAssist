import { useCallback, useEffect, useState } from 'react'
import { mcpApi } from '../api/mcpApi'
import type { MCPServer, MCPServerInfo } from '../types'
import { useToast } from '../../../context/ToastContext'

export const useMcpManager = () => {
  const { toast } = useToast()

  const [info, setInfo] = useState<MCPServerInfo | null>(null)
  const [servers, setServers] = useState<MCPServer[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [infoData, serversData] = await Promise.all([
        mcpApi.getMcpInfo().catch(() => null),
        mcpApi.listMcpServers().catch(() => []),
      ])
      if (infoData) setInfo(infoData)
      setServers(serversData)
    } catch {
      toast.error('Error al sincronizar datos de MCP.', 'Error de Conexión')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const addServer = async (payload: {
    name: string
    transport: 'sse' | 'http'
    url: string
    headers?: Record<string, string>
    enabled?: boolean
  }) => {
    setActionLoading('create')
    try {
      const newServer = await mcpApi.createMcpServer(payload)
      setServers((prev) => [newServer, ...prev])
      toast.success(`Servidor MCP '${newServer.name}' registrado exitosamente.`, 'Servidor Agregado')
      // Automatically ping to sync initial tools
      void pingServer(newServer.id)
      return newServer
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al registrar el servidor'
      toast.error(msg, 'Error')
      throw err
    } finally {
      setActionLoading(null)
    }
  }

  const toggleServer = async (server: MCPServer) => {
    const nextState = !server.enabled
    setActionLoading(`toggle-${server.id}`)
    try {
      const updated = await mcpApi.updateMcpServer(server.id, { enabled: nextState })
      setServers((prev) => prev.map((s) => (s.id === server.id ? updated : s)))
      toast.success(
        `Servidor '${server.name}' ${nextState ? 'habilitado' : 'deshabilitado'}.`,
        'Estado Actualizado',
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al actualizar el estado'
      toast.error(msg, 'Error')
    } finally {
      setActionLoading(null)
    }
  }

  const removeServer = async (id: string, name: string) => {
    setActionLoading(`delete-${id}`)
    try {
      await mcpApi.deleteMcpServer(id)
      setServers((prev) => prev.filter((s) => s.id !== id))
      toast.success(`Servidor '${name}' eliminado.`, 'Servidor Removido')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al eliminar servidor'
      toast.error(msg, 'Error')
    } finally {
      setActionLoading(null)
    }
  }

  const pingServer = async (id: string) => {
    setActionLoading(`ping-${id}`)
    try {
      const res = await mcpApi.pingMcpServer(id)
      if (res.success) {
        toast.success(res.message, 'Conexión Exitosa')
        setServers((prev) =>
          prev.map((s) => (s.id === id ? { ...s, cached_tools: res.tools } : s)),
        )
      } else {
        toast.error(res.message, 'Fallo de Conexión')
      }
      return res
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al conectar con servidor MCP'
      toast.error(msg, 'Fallo de Conexión')
    } finally {
      setActionLoading(null)
    }
  }

  const testTool = async (serverId: string, toolName: string, args: Record<string, any> = {}) => {
    setActionLoading(`call-${serverId}-${toolName}`)
    try {
      const res = await mcpApi.callMcpTool(serverId, toolName, args)
      toast.success(`Herramienta '${toolName}' ejecutada correctamente.`, 'Resultado MCP')
      return res.result
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error invocando herramienta'
      toast.error(msg, 'Error MCP')
      throw err
    } finally {
      setActionLoading(null)
    }
  }

  return {
    info,
    servers,
    loading,
    actionLoading,
    refresh: loadData,
    addServer,
    toggleServer,
    removeServer,
    pingServer,
    testTool,
  }
}
