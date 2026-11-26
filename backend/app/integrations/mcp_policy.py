"""Authorization policy for tools exposed by external MCP servers.

Pure functions, no I/O. The rules, in order:

1. Default deny: a tool nobody approved cannot run.
2. An administrator approves each tool and classifies it as read-only or not.
3. The approval is pinned to a fingerprint of the tool's name, description and input schema. If the
   server later changes any of them (a "rug pull"), the approval stops applying until it is renewed.
4. A tool that is not read-only additionally needs the user's explicit confirmation on every call.
5. Arguments are validated against the approved schema, and unknown fields are rejected.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

MAX_ARGUMENTS_BYTES = 64 * 1024
MAX_ERRORS_REPORTED = 5


@dataclass(frozen=True)
class ToolDescriptor:
  """A tool as the MCP server currently advertises it."""

  name: str
  description: str = ""
  input_schema: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class PolicyDecision:
  allowed: bool
  reason: str = ""
  requires_confirmation: bool = False


def tool_fingerprint(name: str, description: str, input_schema: Optional[dict[str, Any]]) -> str:
  """Stable hash of everything the model sees about a tool."""
  seen = {"name": name, "description": description or "", "input_schema": input_schema or {}}
  canonical = json.dumps(seen, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
  return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def descriptor_fingerprint(descriptor: ToolDescriptor) -> str:
  return tool_fingerprint(descriptor.name, descriptor.description, descriptor.input_schema)


def _tool_entry(item: Any) -> Optional[dict[str, Any]]:
  """One approval entry from a stored item, or None when the item is neither a name nor an object with one."""
  if isinstance(item, str):
    return {"name": item.strip(), "read_only": True, "approved": False, "fingerprint": None, "input_schema": None}
  if not (isinstance(item, dict) and isinstance(item.get("name"), str)):
    return None
  return {
    "name": item["name"].strip(),
    "read_only": bool(item.get("read_only", False)),
    "approved": bool(item.get("approved", False)) and bool(item.get("fingerprint")),
    "fingerprint": item.get("fingerprint"),
    "input_schema": item.get("input_schema") if isinstance(item.get("input_schema"), dict) else None,
    "approved_by": item.get("approved_by"),
    "approved_at": item.get("approved_at"),
  }


def normalize_tools(raw: Any) -> list[dict[str, Any]]:
  """Approval entries from storage.

  Legacy entries (a bare tool name) are kept but unapproved and unpinned, so they authorize nothing
  until an administrator approves them again.
  """
  entries: list[dict[str, Any]] = []
  seen: set[str] = set()
  for item in raw or []:
    entry = _tool_entry(item)
    if entry is None or not entry["name"] or entry["name"] in seen:
      continue
    seen.add(entry["name"])
    entries.append(entry)
  return entries


def approved_names(entries: Iterable[dict[str, Any]]) -> list[str]:
  return [e["name"] for e in entries if e.get("approved")]


def approve_tool(
  entries: Iterable[dict[str, Any]],
  descriptor: ToolDescriptor,
  *,
  read_only: bool,
  approved_by: Optional[str] = None,
) -> list[dict[str, Any]]:
  """Add or renew the approval of one tool, pinned to what the administrator just reviewed."""
  if descriptor.input_schema is not None:
    try:
      Draft202012Validator.check_schema(descriptor.input_schema)
    except SchemaError as exc:
      raise ValueError(f"The tool input schema is not valid: {exc.message}") from exc
  updated = [e for e in normalize_tools(entries) if e["name"] != descriptor.name.strip()]
  approval = {"name": descriptor.name.strip(), "read_only": bool(read_only), "approved": True, "fingerprint": descriptor_fingerprint(descriptor)}
  approval.update(input_schema=copy.deepcopy(descriptor.input_schema), approved_by=approved_by, approved_at=datetime.now(timezone.utc).isoformat())
  updated.append(approval)
  return updated


def revoke_tool(entries: Iterable[dict[str, Any]], name: str) -> list[dict[str, Any]]:
  return [e for e in normalize_tools(entries) if e["name"] != name.strip()]


def authorize_call(entries: Iterable[dict[str, Any]], descriptor: ToolDescriptor, *, user_confirmed: bool = False) -> PolicyDecision:
  """Decide whether `descriptor` may run now, comparing it with what was approved."""
  entry = next((e for e in normalize_tools(entries) if e["name"] == descriptor.name), None)
  if entry is None or not entry["approved"]:
    return PolicyDecision(False, f"The tool '{descriptor.name}' is not approved by an administrator.")
  if entry["fingerprint"] != descriptor_fingerprint(descriptor):
    return PolicyDecision(
      False,
      f"The tool '{descriptor.name}' changed since it was approved; an administrator must review and approve it again.",
    )
  if not entry["read_only"] and not user_confirmed:
    return PolicyDecision(False, f"The tool '{descriptor.name}' can change things and needs the user's confirmation.", True)
  return PolicyDecision(True)


def _strict(schema: dict[str, Any]) -> dict[str, Any]:
  """Reject unknown top-level fields unless the schema says otherwise."""
  strict = copy.deepcopy(schema)
  if strict.get("type", "object") == "object" and "additionalProperties" not in strict:
    strict["additionalProperties"] = False
  return strict


def validate_arguments(schema: Optional[dict[str, Any]], arguments: Any) -> list[str]:
  """Problems found in `arguments` (empty when valid)."""
  if not isinstance(arguments, dict):
    return ["Arguments must be an object."]
  try:
    size = len(json.dumps(arguments, default=str))
  except (TypeError, ValueError):
    return ["Arguments are not serializable."]
  if size > MAX_ARGUMENTS_BYTES:
    return [f"Arguments exceed {MAX_ARGUMENTS_BYTES} bytes."]
  effective = _strict(schema) if schema else {"type": "object", "additionalProperties": False}
  validator = Draft202012Validator(effective)
  errors = sorted(validator.iter_errors(arguments), key=lambda e: list(e.path))
  return [
    (f"{'.'.join(str(p) for p in e.path)}: " if e.path else "") + e.message
    for e in errors[:MAX_ERRORS_REPORTED]
  ]


# ----------------------------------------------------------------- destinations (browser-like tools)

# Argument names that carry a place to go to. A tool that navigates can send data out in the URL, so
# every destination must be on the server's allowed domains. With none configured, none is allowed.
DESTINATION_ARGUMENTS = frozenset({
  "url", "uri", "href", "link", "target", "endpoint", "address", "page", "website", "origin", "destination", "to",
})
_URL_LIKE = re.compile(r"^(?:https?:)?//[^\s/]+", re.IGNORECASE)
_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_domain(value: Any) -> str:
  """A bare lowercase host name, or raises ValueError. Schemes, paths, ports and wildcards are not domains."""
  text = str(value or "").strip().lower().rstrip(".")
  if not _DOMAIN.match(text):
    raise ValueError(f"'{value}' is not a valid domain name. Use a bare host such as docs.example.com.")
  return text


def normalize_domains(values: Iterable[Any]) -> list[str]:
  out: list[str] = []
  for value in values or []:
    domain = normalize_domain(value)
    if domain not in out:
      out.append(domain)
  return out


def _leaf_strings(value: Any, key: str = "") -> Iterator[tuple[str, str]]:
  """Every string in nested arguments, with the lowercase name of the nearest key above it."""
  if isinstance(value, dict):
    for k, v in value.items():
      yield from _leaf_strings(v, str(k).lower())
  elif isinstance(value, (list, tuple)):
    for item in value:
      yield from _leaf_strings(item, key)
  elif isinstance(value, str):
    yield key, value.strip()


def extract_destinations(arguments: Any) -> list[str]:
  """Every URL-like value in the arguments: under a destination-like name or written as a URL."""
  if not isinstance(arguments, dict):
    return []
  return [text for key, text in _leaf_strings(arguments) if key in DESTINATION_ARGUMENTS and text or _URL_LIKE.match(text)]


_SCHEME_PREFIX = re.compile(r"^[a-z][a-z0-9+.-]*:(?!\d)", re.IGNORECASE)


def _as_url(text: str) -> Optional[str]:
  """The text as an absolute URL; a bare host gets https. None when it carries another scheme."""
  if text.startswith("//"):
    return "https:" + text
  if "://" in text:
    return text
  # "javascript:alert(1)" or "mailto:x" carry a scheme; "docs.example.com:8080" is a host and a port.
  return None if _SCHEME_PREFIX.match(text) else "https://" + text


def destination_host(value: str) -> Optional[str]:
  """The host of a destination, or None when it is not a plain http(s) URL."""
  url = _as_url(value.strip())
  if url is None:
    return None
  try:
    parsed = urlparse(url)
  except ValueError:
    return None
  if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
    return None
  return (parsed.hostname or "").lower().rstrip(".") or None


def host_allowed(host: str, allowed_domains: Iterable[str]) -> bool:
  """Exact match or a subdomain of an allowed domain (never a look-alike suffix)."""
  return any(host == domain or host.endswith("." + domain) for domain in allowed_domains)


def check_destinations(arguments: Any, allowed_domains: Optional[Iterable[str]]) -> list[str]:
  """Problems with the places the arguments point to (empty when there is nothing to object to)."""
  allowed = normalize_domains(allowed_domains or [])
  problems: list[str] = []
  for destination in extract_destinations(arguments):
    host = destination_host(destination)
    if host is None:
      problems.append(f"'{destination[:80]}' is not an acceptable destination.")
    elif not allowed:
      problems.append(f"No destination is allowed for this server; '{host}' was requested.")
    elif not host_allowed(host, allowed):
      problems.append(f"'{host}' is not among the domains allowed for this server.")
  return problems
