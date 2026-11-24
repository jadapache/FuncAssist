"""MCP Tool and Integration Executor Interface.

Provides a unified, secure executor interface for LLM orchestration to invoke external
integration tools, checking organization permissions, safe credential resolution,
and SSRF prevention for remote MCP server endpoints.
"""

from __future__ import annotations

import hashlib
import inspect
import ipaddress
import json
import logging
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.integrations.mcp_policy import ToolDescriptor, authorize_call, normalize_tools, validate_arguments

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


INTEGRATION_PROVIDERS = frozenset({"github", "gitlab", "jira"})
# Jira connections are personal: the call always runs with the authenticated user's own token.
PERSONAL_PROVIDERS = frozenset({"jira"})
# Arguments the caller (ultimately the model) may never choose.
RESERVED_ARGUMENTS = frozenset({"self", "user_id"})
_AUDIT = logging.getLogger("funcassist.tool_audit")


def _arguments_digest(arguments: Any) -> str:
  """Stable short hash of the arguments, so the audit log never stores their content."""
  try:
    raw = json.dumps(arguments, sort_keys=True, default=str)
  except (TypeError, ValueError):
    raw = repr(arguments)
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class IntegrationToolExecutor:
  """Safe dispatch and execution adapter for external tools and MCP endpoints.

  Default deny: a tool runs only when it is in the explicit `allowed_tools` list AND it is one of the
  adapter's read-only capabilities. Connection management (`connect_*`, `disconnect`, `update_*`,
  `start_oauth`) is never reachable from here.
  """

  def __init__(self, organization_id: str = "default", user_id: Optional[str] = None):
    self.organization_id = organization_id
    self.user_id = user_id
    self.http_client = SafeMCPHttpClient()

  def can_invoke_tool(self, provider: str, tool_name: str, allowed_tools: Optional[list[str]]) -> bool:
    """An explicit allowlist only: an empty list or a wildcard authorizes nothing."""
    return bool(allowed_tools) and tool_name in allowed_tools

  def _audit(self, provider: str, tool_name: str, arguments: Any, decision: str, reason: str = "") -> None:
    _AUDIT.info(
      "tool_call user=%s org=%s provider=%s tool=%s args=%s decision=%s%s",
      self.user_id, self.organization_id, provider, tool_name, _arguments_digest(arguments), decision,
      f" reason={reason}" if reason else "",
    )

  def _deny(self, provider: str, tool_name: str, arguments: Any, error: str) -> dict[str, Any]:
    self._audit(provider, tool_name, arguments, "denied", error)
    return {"ok": False, "error": error}

  async def execute_tool(
    self,
    provider: str,
    tool_name: str,
    arguments: dict[str, Any],
    allowed_tools: Optional[list[str]] = None,
  ) -> dict[str, Any]:
    """Execute a validated read-only operation against an integration adapter.

    Never returns or leaks credentials to the caller. Every decision is audited (arguments by hash).
    """
    if not self.can_invoke_tool(provider, tool_name, allowed_tools):
      return self._deny(provider, tool_name, arguments, f"Tool '{tool_name}' is not authorized for provider '{provider}'.")

    if provider.startswith("mcp:"):
      return self._deny(
        provider, tool_name, arguments,
        f"Remote MCP client protocol for '{provider}' is configured but remote session transport is in extension-point mode.",
      )

    if provider not in INTEGRATION_PROVIDERS:
      return self._deny(provider, tool_name, arguments, f"Provider '{provider}' has no registered execution adapter.")

    if not isinstance(arguments, dict):
      return self._deny(provider, tool_name, arguments, "Tool arguments must be an object.")

    from app.integrations.registry import registry

    try:
      adapter = registry.get(provider)
    except KeyError:
      return self._deny(provider, tool_name, arguments, f"Provider '{provider}' has no registered execution adapter.")

    read_only = {capability.value for capability in adapter.get_capabilities()}
    method = getattr(adapter, tool_name, None) if tool_name in read_only else None
    if not callable(method):
      return self._deny(provider, tool_name, arguments, f"Method '{tool_name}' is not a read-only tool of adapter '{provider}'.")

    signature = inspect.signature(method)
    accepted = {
      name for name, param in signature.parameters.items()
      if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    } - RESERVED_ARGUMENTS
    rejected = sorted(set(arguments) - accepted)
    if rejected:
      return self._deny(provider, tool_name, arguments, f"Argument not allowed for '{tool_name}': {', '.join(rejected)}.")

    call_args = dict(arguments)
    if provider in PERSONAL_PROVIDERS:
      if not self.user_id:
        return self._deny(provider, tool_name, arguments, f"{provider} is a personal integration: a user is required.")
      call_args["user_id"] = self.user_id  # always the caller; never a value chosen by the model

    try:
      result = await method(**call_args)
    except Exception as exc:
      self._audit(provider, tool_name, arguments, "error", type(exc).__name__)
      return {"ok": False, "error": str(exc)}
    self._audit(provider, tool_name, arguments, "allowed")
    return {"ok": True, "result": result}

  async def execute_mcp_tool(
    self,
    server: dict[str, Any],
    descriptor: ToolDescriptor,
    arguments: Any,
    *,
    user_confirmed: bool = False,
  ) -> dict[str, Any]:
    """Authorize a call to a tool of an MCP server an administrator enabled.

    The policy runs before any transport exists: the tool must be approved, unchanged since its approval
    and, when it can change things, confirmed by the user; the arguments must match the approved schema.
    The remote session transport itself is not enabled yet, so a call that passes still does not run.
    """
    provider = f"mcp:{server.get('id') or server.get('name')}"
    decision = authorize_call(server.get("tools"), descriptor, user_confirmed=user_confirmed)
    if not decision.allowed:
      denied = self._deny(provider, descriptor.name, arguments, decision.reason)
      if decision.requires_confirmation:
        denied["requires_confirmation"] = True
      return denied

    entry = next(e for e in normalize_tools(server.get("tools")) if e["name"] == descriptor.name)
    problems = validate_arguments(entry.get("input_schema"), arguments)
    if problems:
      return self._deny(provider, descriptor.name, arguments, "Invalid arguments: " + "; ".join(problems))

    return self._deny(
      provider, descriptor.name, arguments,
      "The remote MCP session transport is not enabled yet; the call was authorized but not sent.",
    )
