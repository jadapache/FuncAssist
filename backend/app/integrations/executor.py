"""MCP Tool and Integration Executor Interface.

Provides a unified, secure executor interface for LLM orchestration to invoke external
integration tools, checking organization permissions, safe credential resolution,
and SSRF prevention for remote MCP server endpoints.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import json
import logging
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.ai.logging import log_security_event
from app.integrations.mcp_policy import (
  ToolDescriptor,
  authorize_call,
  check_destinations,
  extract_destinations,
  normalize_tools,
  validate_arguments,
)

logger = logging.getLogger(__name__)

# Standard permitted external web ports for MCP SSE / HTTP endpoints (the schemes are those of _DEFAULT_PORTS)
ALLOWED_MCP_PORTS = {80, 443, 8080, 8443}


# Carrier-grade NAT (RFC 6598) is neither "private" nor "global" for the ipaddress module's flags.
_CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")
_UNSAFE_IP_FLAGS = ("is_loopback", "is_private", "is_link_local", "is_multicast", "is_reserved", "is_unspecified")
_DEFAULT_PORTS = {"https": 443, "http": 80}
_INTERNAL_HOSTNAMES = frozenset({"localhost", "metadata.google.internal", "instance-data"})


def validate_mcp_ip_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
  """Validate IP address object against private, loopback, link-local, reserved and carrier-grade NAT ranges."""
  return not any(getattr(ip, flag) for flag in _UNSAFE_IP_FLAGS) and ip not in _CARRIER_GRADE_NAT


def _is_internal_hostname(hostname: str) -> bool:
  name = hostname.lower()
  return name in _INTERNAL_HOSTNAMES or name.endswith(".local")


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
  try:
    return ipaddress.ip_address(host)
  except ValueError:
    return None


def _resolves_only_to_public_addresses(hostname: str, port: int) -> bool:
  """Every A and AAAA record of the host must be public, so a domain cannot point into the internal network."""
  infos = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
  return all(validate_mcp_ip_address(ipaddress.ip_address(info[4][0])) for info in infos)


def _is_safe_endpoint(url: str, resolve_dns: bool) -> bool:
  parsed = urlparse(url.strip())
  scheme = parsed.scheme.lower()
  hostname = parsed.hostname
  default_port = _DEFAULT_PORTS.get(scheme)
  if default_port is None:
    return False
  if not hostname:
    return False
  port = parsed.port or default_port
  if port not in ALLOWED_MCP_PORTS or _is_internal_hostname(hostname):
    return False
  raw_ip = _parse_ip(hostname)
  if raw_ip is not None:
    return validate_mcp_ip_address(raw_ip)
  return not resolve_dns or _resolves_only_to_public_addresses(hostname, port)


def validate_mcp_endpoint_url(url: str, resolve_dns: bool = True) -> bool:
  """Validate endpoint URL against SSRF, internal network pivots, and private IPs.

  Performs scheme verification, port restriction, hostname filtering, and live DNS
  resolution to check IPv4 and IPv6 addresses against private and cloud-metadata subnets.
  Anything that cannot be parsed or resolved is rejected.
  """
  try:
    return _is_safe_endpoint(url, resolve_dns)
  except Exception:
    return False


class SafeMCPHttpClient:
  """HTTP Client wrapper for MCP server communication that guards against SSRF redirects."""

  def __init__(self, timeout: float = 15.0):
    self.timeout = timeout

  async def post(self, url: str, json_data: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
    if not validate_mcp_endpoint_url(url):
      raise ValueError(f"Endpoint '{url}' rejected by SSRF security policy.")

    async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
      response = await client.post(url, json=json_data, headers=headers)

      # If response is a redirect, validate the redirect target before following
      if response.is_redirect:
        redirect_url = response.headers.get("Location")
        if not redirect_url or not validate_mcp_endpoint_url(redirect_url):
          raise ValueError(f"SSRF Alert: Redirect target '{redirect_url}' is not permitted.")

      return response


INTEGRATION_PROVIDERS = frozenset({"github", "gitlab", "jira"})
# Jira connections are personal: the call always runs with the authenticated user's own token.
PERSONAL_PROVIDERS = frozenset({"jira"})
# Arguments the caller (ultimately the model) may never choose.
RESERVED_ARGUMENTS = frozenset({"self", "user_id"})
_AUDIT = logging.getLogger("funcassist.tool_audit")


def _keyword_parameters(method: Any) -> set[str]:
  kinds = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
  return {p.name for p in inspect.signature(method).parameters.values() if p.kind in kinds}


def _no_adapter(provider: str) -> str:
  return f"Provider '{provider}' has no registered execution adapter."


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
    digest = _arguments_digest(arguments)
    reason_suffix = f" reason={reason}" if reason else ""
    event_reason = reason or None
    _AUDIT.info(
      "tool_call user=%s org=%s provider=%s tool=%s args=%s decision=%s%s",
      self.user_id, self.organization_id, provider, tool_name, digest, decision, reason_suffix,
    )
    log_security_event(
      "tool_call", user=self.user_id, org=self.organization_id, provider=provider, tool=tool_name,
      args=digest, decision=decision, reason=event_reason,
    )

  def _deny(
    self, provider: str, tool_name: str, arguments: Any, error: str, *, audit_reason: str | None = None
  ) -> dict[str, Any]:
    """`error` goes back to the caller; the audit log gets `audit_reason` when the error quotes values."""
    self._audit(provider, tool_name, arguments, "denied", audit_reason or error)
    return {"ok": False, "error": error}

  def _refusal(self, provider: str, tool_name: str, arguments: Any, allowed_tools: Optional[list[str]]) -> str:
    """Why the call cannot even be looked up, or an empty string when it can."""
    if not self.can_invoke_tool(provider, tool_name, allowed_tools):
      return f"Tool '{tool_name}' is not authorized for provider '{provider}'."
    if provider.startswith("mcp:"):
      return f"Remote MCP client protocol for '{provider}' is configured but remote session transport is in extension-point mode."
    if provider not in INTEGRATION_PROVIDERS:
      return _no_adapter(provider)
    if not isinstance(arguments, dict):
      return "Tool arguments must be an object."
    return ""

  @staticmethod
  def _read_only_method(provider: str, tool_name: str) -> tuple[Any, str]:
    """The adapter method behind a tool, only when the adapter declares it a read-only capability."""
    from app.integrations.registry import registry

    try:
      adapter = registry.get(provider)
    except KeyError:
      return None, _no_adapter(provider)
    read_only = {capability.value for capability in adapter.get_capabilities()}
    method = getattr(adapter, tool_name, None) if tool_name in read_only else None
    if not callable(method):
      return None, f"Method '{tool_name}' is not a read-only tool of adapter '{provider}'."
    return method, ""

  def _bind_arguments(
    self, provider: str, tool_name: str, method: Any, arguments: dict[str, Any]
  ) -> tuple[dict[str, Any] | None, str]:
    """The keyword arguments of the call: only those the method accepts, plus the caller for personal providers."""
    accepted = _keyword_parameters(method) - RESERVED_ARGUMENTS
    rejected = sorted(set(arguments) - accepted)
    if rejected:
      return None, f"Argument not allowed for '{tool_name}': {', '.join(rejected)}."
    if provider not in PERSONAL_PROVIDERS:
      return dict(arguments), ""
    if not self.user_id:
      return None, f"{provider} is a personal integration: a user is required."
    return {**arguments, "user_id": self.user_id}, ""  # always the caller; never a value chosen by the model

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
    error = self._refusal(provider, tool_name, arguments, allowed_tools)
    if error:
      return self._deny(provider, tool_name, arguments, error)

    method, error = self._read_only_method(provider, tool_name)
    if method is None:
      return self._deny(provider, tool_name, arguments, error)

    call_args, error = self._bind_arguments(provider, tool_name, method, arguments)
    if call_args is None:
      return self._deny(provider, tool_name, arguments, error)

    try:
      result = await method(**call_args)
    except Exception as exc:
      self._audit(provider, tool_name, arguments, "error", type(exc).__name__)
      return {"ok": False, "error": str(exc)}
    self._audit(provider, tool_name, arguments, "allowed")
    return {"ok": True, "result": result}

  async def _destination_denial(
    self, provider: str, tool_name: str, arguments: Any, server: dict[str, Any]
  ) -> dict[str, Any] | None:
    """A tool that navigates or fetches can send data out in the URL: every destination must be on the
    server's allowed domains and must not point into the internal network."""
    problems = check_destinations(arguments, server.get("allowed_domains"))
    if problems:
      return self._deny(
        provider, tool_name, arguments, "Destination not allowed: " + "; ".join(problems),
        audit_reason="destination_not_allowed",
      )
    for destination in extract_destinations(arguments):
      url = destination if "://" in destination else "https://" + destination.lstrip("/")
      if not await asyncio.to_thread(validate_mcp_endpoint_url, url):
        return self._deny(
          provider, tool_name, arguments, "Destination not allowed: it points to a private or unsafe address.",
          audit_reason="destination_private_address",
        )
    return None

  async def execute_mcp_tool(self, server: dict[str, Any], descriptor: ToolDescriptor, arguments: Any, *, user_confirmed: bool = False) -> dict[str, Any]:
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
      return self._deny(
        provider, descriptor.name, arguments, "Invalid arguments: " + "; ".join(problems), audit_reason="invalid_arguments"
      )

    denial = await self._destination_denial(provider, descriptor.name, arguments, server)
    if denial:
      return denial

    return self._deny(
      provider, descriptor.name, arguments,
      "The remote MCP session transport is not enabled yet; the call was authorized but not sent.",
    )
