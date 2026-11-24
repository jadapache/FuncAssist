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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

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
  canonical = json.dumps(
    {"name": name, "description": description or "", "input_schema": input_schema or {}},
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
  )
  return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def descriptor_fingerprint(descriptor: ToolDescriptor) -> str:
  return tool_fingerprint(descriptor.name, descriptor.description, descriptor.input_schema)


def normalize_tools(raw: Any) -> list[dict[str, Any]]:
  """Approval entries from storage.

  Legacy entries (a bare tool name) are kept but unapproved and unpinned, so they authorize nothing
  until an administrator approves them again.
  """
  entries: list[dict[str, Any]] = []
  seen: set[str] = set()
  for item in raw or []:
    if isinstance(item, str):
      entry = {"name": item.strip(), "read_only": True, "approved": False, "fingerprint": None, "input_schema": None}
    elif isinstance(item, dict) and isinstance(item.get("name"), str):
      entry = {
        "name": item["name"].strip(),
        "read_only": bool(item.get("read_only", False)),
        "approved": bool(item.get("approved", False)) and bool(item.get("fingerprint")),
        "fingerprint": item.get("fingerprint"),
        "input_schema": item.get("input_schema") if isinstance(item.get("input_schema"), dict) else None,
        "approved_by": item.get("approved_by"),
        "approved_at": item.get("approved_at"),
      }
    else:
      continue
    if not entry["name"] or entry["name"] in seen:
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
  updated.append({
    "name": descriptor.name.strip(),
    "read_only": bool(read_only),
    "approved": True,
    "fingerprint": descriptor_fingerprint(descriptor),
    "input_schema": copy.deepcopy(descriptor.input_schema),
    "approved_by": approved_by,
    "approved_at": datetime.now(timezone.utc).isoformat(),
  })
  return updated


def revoke_tool(entries: Iterable[dict[str, Any]], name: str) -> list[dict[str, Any]]:
  return [e for e in normalize_tools(entries) if e["name"] != name.strip()]


def authorize_call(
  entries: Iterable[dict[str, Any]],
  descriptor: ToolDescriptor,
  *,
  user_confirmed: bool = False,
) -> PolicyDecision:
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
