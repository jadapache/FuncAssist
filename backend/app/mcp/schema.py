"""MCP (Model Context Protocol) Schemas for standard JSON-RPC 2.0 and agentic tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# --- JSON-RPC 2.0 Base Models ---

class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


# --- MCP Tool and Resource Primitives ---

class MCPTool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


class MCPToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPToolContent(BaseModel):
    type: str = "text"
    text: str


class MCPToolCallResult(BaseModel):
    content: List[MCPToolContent]
    isError: bool = False


class MCPResource(BaseModel):
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = "application/json"


class MCPResourceContent(BaseModel):
    uri: str
    mimeType: Optional[str] = "application/json"
    text: Optional[str] = None
    blob: Optional[str] = None


# --- External MCP Server Configuration Models ---

class MCPServerConfig(BaseModel):
    id: str
    name: str
    transport: str = "sse"  # "sse" | "http"
    url: str
    command: Optional[str] = None
    args: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    enabled: bool = True
    cached_tools: List[MCPTool] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MCPServerCreate(BaseModel):
    name: str
    transport: str = "sse"
    url: str
    headers: Optional[Dict[str, str]] = None
    enabled: bool = True


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    transport: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None


class MCPServerCallToolRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
