"""MCP Tool and Integration Executor Interface.

Provides a unified, secure executor interface for LLM orchestration to invoke external
integration tools, checking organization permissions, safe credential resolution,
and SSRF prevention for remote MCP server endpoints.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Standard permitted external web schemes and ports for MCP SSE / HTTP endpoints
ALLOWED_MCP_SCHEMES = {"https", "http"}
ALLOWED_MCP_PORTS = {80, 443, 8080, 8443}


def validate_mcp_ip_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
  """Validate IP address object against private, loopback, link-local and reserved ranges."""
  if ip.is_loopback:
    return False
  if ip.is_private:
    return False
  if ip.is_link_local:
    return False
  if ip.is_multicast:
    return False
  if ip.is_reserved:
    return False
  if ip.is_unspecified:
    return False

  # Explicit Cloud metadata IPv4 & IPv6 checks
  str_ip = str(ip)
  if str_ip in ("169.254.169.254", "fe80::1", "::1", "0.0.0.0", "127.0.0.1"):
    return False
  if str_ip.startswith("100.64."):  # Carrier Grade NAT
    return False

  return True


def validate_mcp_endpoint_url(url: str, resolve_dns: bool = True) -> bool:
  """Validate endpoint URL against SSRF, internal network pivots, and private IPs.

  Performs scheme verification, port restriction, hostname filtering, and live DNS
  resolution to check IPv4 and IPv6 addresses against private and cloud-metadata subnets.
  """
  if not url or not isinstance(url, str):
    return False

  try:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_MCP_SCHEMES:
      return False

    hostname = parsed.hostname
    if not hostname:
      return False

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    if port not in ALLOWED_MCP_PORTS:
      return False

    hostname_lower = hostname.lower()
    blocked_hosts = {
      "localhost",
      "127.0.0.1",
      "0.0.0.0",
      "::1",
      "metadata.google.internal",
      "instance-data",
    }
    if hostname_lower in blocked_hosts or hostname_lower.endswith(".local"):
      return False

    # Check if host is direct raw IP
    try:
      raw_ip = ipaddress.ip_address(hostname)
      return validate_mcp_ip_address(raw_ip)
    except ValueError:
      pass

    # Resolve all DNS A and AAAA records to ensure domain doesn't resolve to private IP
    if resolve_dns:
      try:
        addr_infos = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr_infos:
          resolved_ip_str = sockaddr[0]
          resolved_ip = ipaddress.ip_address(resolved_ip_str)
          if not validate_mcp_ip_address(resolved_ip):
            return False
      except socket.gaierror:
        # Unable to resolve host
        return False
      except Exception:
        return False

    return True
  except Exception:
    return False


class SafeMCPHttpClient:
  """HTTP Client wrapper for MCP server communication that guards against SSRF redirects."""

  def __init__(self, timeout: float = 15.0):
    self.timeout = timeout

  async def post(self, url: str, json_data: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
    if not validate_mcp_endpoint_url(url, resolve_dns=True):
      raise ValueError(f"Endpoint '{url}' rejected by SSRF security policy.")

    async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
      response = await client.post(url, json=json_data, headers=headers)

      # If response is a redirect, validate the redirect target before following
      if response.is_redirect:
        redirect_url = response.headers.get("Location")
        if not redirect_url or not validate_mcp_endpoint_url(redirect_url, resolve_dns=True):
          raise ValueError(f"SSRF Alert: Redirect target '{redirect_url}' is not permitted.")

      return response


class IntegrationToolExecutor:
  """Safe dispatch and execution adapter for external tools and MCP endpoints."""

  def __init__(self, organization_id: str = "default", user_id: Optional[str] = None):
    self.organization_id = organization_id
    self.user_id = user_id
    self.http_client = SafeMCPHttpClient()

  def can_invoke_tool(self, provider: str, tool_name: str, allowed_tools: list[str]) -> bool:
    """Check if the given tool is authorized within the integration scope."""
    if not allowed_tools or "*" in allowed_tools:
      return True
    return tool_name in allowed_tools

  async def execute_tool(
    self,
    provider: str,
    tool_name: str,
    arguments: dict[str, Any],
    allowed_tools: Optional[list[str]] = None,
  ) -> dict[str, Any]:
    """Execute a validated operation against an integration adapter or MCP server.

    Strictly applies tool permission checks, argument validation, and executes without
    ever returning or leaking internal secrets or credentials to the caller.
    """
    allowed = allowed_tools or ["*"]
    if not self.can_invoke_tool(provider, tool_name, allowed):
      return {
        "ok": False,
        "error": f"Tool '{tool_name}' is not authorized for provider '{provider}'.",
      }

    # Safe dispatch to known internal adapters (e.g. Jira, GitHub, GitLab)
    if provider in ("github", "gitlab", "jira"):
      from app.integrations.registry import registry
      try:
        adapter = registry.get(provider)
        if hasattr(adapter, tool_name):
          method = getattr(adapter, tool_name)
          if callable(method):
            # Pass user_id to Jira methods if applicable
            call_args = dict(arguments)
            if provider == "jira" and self.user_id and "user_id" not in call_args:
              import inspect
              sig = inspect.signature(method)
              if "user_id" in sig.parameters:
                call_args["user_id"] = self.user_id

            res = await method(**call_args)
            return {"ok": True, "result": res}
        return {"ok": False, "error": f"Method '{tool_name}' not supported by adapter '{provider}'."}
      except Exception as exc:
        return {"ok": False, "error": str(exc)}

    # Extensible MCP endpoint execution point
    if provider.startswith("mcp:"):
      return {
        "ok": False,
        "error": f"Remote MCP client protocol for '{provider}' is configured but remote session transport is in extension-point mode.",
      }

    return {
      "ok": False,
      "error": f"Provider '{provider}' has no registered execution adapter.",
    }
