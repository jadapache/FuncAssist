import { API_BASE, getAuthHeaders, handleResponse } from '../../../api/client'
import type { MCPServer, MCPServerInfo, MCPTool } from '../types'

export const mcpApi = {
  getMcpInfo: async (): Promise<MCPServerInfo> => {
    const res = await fetch(`${API_BASE}/api/mcp/info`, {
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
    })
    return handleResponse<MCPServerInfo>(res)
  },

  listMcpServers: async (): Promise<MCPServer[]> => {
    const res = await fetch(`${API_BASE}/api/mcp/servers`, {
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
    })
    return handleResponse<MCPServer[]>(res)
  },

  createMcpServer: async (payload: {
    name: string
    transport: 'sse' | 'http'
    url: string
    headers?: Record<string, string>
    enabled?: boolean
  }): Promise<MCPServer> => {
    const res = await fetch(`${API_BASE}/api/mcp/servers`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify(payload),
    })
    return handleResponse<MCPServer>(res)
  },

  updateMcpServer: async (
    id: string,
    payload: {
      name?: string
      transport?: 'sse' | 'http'
      url?: string
      headers?: Record<string, string>
      enabled?: boolean
    },
  ): Promise<MCPServer> => {
    const res = await fetch(`${API_BASE}/api/mcp/servers/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify(payload),
    })
    return handleResponse<MCPServer>(res)
  },

  deleteMcpServer: async (id: string): Promise<{ message: string; id: string }> => {
    const res = await fetch(`${API_BASE}/api/mcp/servers/${id}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
    })
    return handleResponse<{ message: string; id: string }>(res)
  },

  pingMcpServer: async (
    id: string,
  ): Promise<{
    success: boolean
    message: string
    toolsCount: number
    tools: MCPTool[]
  }> => {
    const res = await fetch(`${API_BASE}/api/mcp/servers/${id}/ping`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
    })
    return handleResponse<{
      success: boolean
      message: string
      toolsCount: number
      tools: MCPTool[]
    }>(res)
  },

  callMcpTool: async (
    id: string,
    toolName: string,
    args: Record<string, any> = {},
  ): Promise<{ success: boolean; result: any }> => {
    const res = await fetch(`${API_BASE}/api/mcp/servers/${id}/call`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        tool_name: toolName,
        arguments: args,
      }),
    })
    return handleResponse<{ success: boolean; result: any }>(res)
  },
}
