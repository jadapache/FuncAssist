"""Edges of the MCP policy and executor: exact fingerprints, defaults of stored entries, limits and audit content."""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

from app.integrations import executor as ex
from app.integrations import mcp_policy as policy
from app.integrations.executor import IntegrationToolExecutor
from app.integrations.mcp_policy import ToolDescriptor

NAVIGATE = ToolDescriptor("navigate", "Open a page", {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]})


# ----------------------------------------------------------------- fingerprint and stored entries


def digest(text: str) -> str:
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_fingerprint_hashes_the_sorted_compact_json_of_what_the_model_sees():
  assert policy.tool_fingerprint("n", "d", {"b": 1, "a": 2}) == digest('{"description":"d","input_schema":{"a":2,"b":1},"name":"n"}')


def test_a_missing_description_or_schema_counts_as_empty():
  assert policy.tool_fingerprint("n", None, None) == digest('{"description":"","input_schema":{},"name":"n"}')
  assert policy.tool_fingerprint("n", "", {}) == policy.tool_fingerprint("n", None, None)


def test_the_fingerprint_keeps_non_ascii_text_as_it_is():
  assert policy.tool_fingerprint("n", "áé", None) == digest('{"description":"áé","input_schema":{},"name":"n"}')


def test_a_legacy_tool_name_is_read_only_but_not_approved():
  [entry] = policy.normalize_tools(["  snapshot "])
  assert entry == {"name": "snapshot", "read_only": True, "approved": False, "fingerprint": None, "input_schema": None}


def test_a_stored_entry_without_flags_is_neither_read_only_nor_approved():
  [entry] = policy.normalize_tools([{"name": "click", "fingerprint": "abc"}])
  assert (entry["read_only"], entry["approved"], entry["fingerprint"]) == (False, False, "abc")


def test_an_approval_without_a_fingerprint_authorizes_nothing():
  [entry] = policy.normalize_tools([{"name": "click", "approved": True}])
  assert entry["approved"] is False


def test_an_approval_records_what_the_administrator_reviewed():
  [entry] = policy.approve_tool([], NAVIGATE, read_only=True, approved_by="admin-1")
  assert (entry["name"], entry["read_only"], entry["approved"], entry["approved_by"]) == ("navigate", True, True, "admin-1")
  assert entry["fingerprint"] == policy.descriptor_fingerprint(NAVIGATE)
  assert entry["input_schema"] == NAVIGATE.input_schema and entry["input_schema"] is not NAVIGATE.input_schema
  assert entry["approved_at"]


def test_a_call_to_a_write_tool_needs_confirmation_unless_the_user_gave_it():
  [entry] = policy.approve_tool([], NAVIGATE, read_only=False)
  denied = policy.authorize_call([entry], NAVIGATE)
  assert (denied.allowed, denied.requires_confirmation) == (False, True)
  assert policy.authorize_call([entry], NAVIGATE, user_confirmed=True).allowed is True


def test_the_arguments_may_be_exactly_the_maximum_size_but_not_one_byte_more():
  fits = {"a": "x" * (policy.MAX_ARGUMENTS_BYTES - 9)}
  assert len(json.dumps(fits)) == policy.MAX_ARGUMENTS_BYTES
  assert policy.validate_arguments({"type": "object", "properties": {"a": {"type": "string"}}}, fits) == []
  too_big = {"a": "x" * (policy.MAX_ARGUMENTS_BYTES - 8)}
  assert policy.validate_arguments({"type": "object", "properties": {"a": {"type": "string"}}}, too_big) == [
    f"Arguments exceed {policy.MAX_ARGUMENTS_BYTES} bytes."
  ]


@pytest.mark.parametrize("value", ["https://user@docs.example.com/", "https://:secret@docs.example.com/", "https://u:p@docs.example.com/"])
def test_a_destination_with_credentials_is_not_acceptable(value):
  assert policy.destination_host(value) is None


def test_a_destination_that_cannot_be_parsed_is_not_acceptable():
  assert policy.destination_host("http://[::1/path") is None


def test_an_unreadable_value_yields_no_host():
  assert policy.destination_host("https://") is None


# ----------------------------------------------------------------- executor


@pytest.fixture
def audit(monkeypatch, caplog):
  caplog.set_level(logging.INFO, logger="funcassist.tool_audit")
  events: list[tuple] = []
  monkeypatch.setattr(ex, "log_security_event", lambda *args, **kwargs: events.append((args, kwargs)))
  return type("Audit", (), {"events": events, "log": lambda self=None: "\n".join(r.getMessage() for r in caplog.records)})()


def server_for(descriptor, read_only=True, domains=("docs.example.com",)):
  tools = policy.approve_tool([], descriptor, read_only=read_only, approved_by="admin")
  return {"id": "srv-1", "tools": tools, "allowed_domains": list(domains)}


@pytest.mark.parametrize("url", ["ftp://example.com:8080/x", "gopher://example.com:8443/x"])
def test_an_endpoint_with_another_scheme_is_refused_whatever_its_port(url):
  assert ex.validate_mcp_endpoint_url(url, resolve_dns=False) is False


@pytest.mark.asyncio
async def test_a_denial_is_audited_with_its_message_as_the_reason(audit):
  executor = IntegrationToolExecutor(organization_id="org-1", user_id="alice")
  result = await executor.execute_tool("jira", "get_issues", {}, allowed_tools=[])
  assert result == {"ok": False, "error": "Tool 'get_issues' is not authorized for provider 'jira'."}
  [(args, kwargs)] = audit.events
  assert args == ("tool_call",)
  assert (kwargs["user"], kwargs["org"], kwargs["provider"], kwargs["tool"], kwargs["decision"]) == (
    "alice", "org-1", "jira", "get_issues", "denied"
  )
  assert kwargs["reason"] == "Tool 'get_issues' is not authorized for provider 'jira'."
  assert "decision=denied reason=Tool 'get_issues' is not authorized" in audit.log()


@pytest.mark.asyncio
async def test_a_denial_that_quotes_values_is_audited_with_its_own_reason(audit):
  executor = IntegrationToolExecutor(user_id="alice")
  result = await executor.execute_mcp_tool(server_for(NAVIGATE), NAVIGATE, {"url": 5})
  assert result["error"].startswith("Invalid arguments")
  assert audit.events[-1][1]["reason"] == "invalid_arguments"
  assert "reason=invalid_arguments" in audit.log() and "Invalid arguments" not in audit.log()


@pytest.mark.asyncio
async def test_a_call_that_is_allowed_is_audited_without_a_reason(audit, monkeypatch):
  class Adapter:
    def get_capabilities(self):
      from app.integrations.base import Capability

      return [Capability.GET_PROJECTS]

    async def get_projects(self, user_id=None):
      return []

  from app.integrations import registry as registry_module

  monkeypatch.setattr(registry_module.registry, "get", lambda provider: Adapter())
  result = await IntegrationToolExecutor(user_id="alice").execute_tool("jira", "get_projects", {}, allowed_tools=["get_projects"])
  assert result == {"ok": True, "result": []}
  assert audit.events[-1][1]["decision"] == "allowed" and audit.events[-1][1]["reason"] is None
  assert "decision=allowed" in audit.log() and "reason=" not in audit.log()


@pytest.mark.asyncio
@pytest.mark.parametrize(
  ("given", "checked"),
  [
    ("docs.example.com/page", "https://docs.example.com/page"),
    ("//docs.example.com/page", "https://docs.example.com/page"),
    ("https://docs.example.com/page", "https://docs.example.com/page"),
    ("http://docs.example.com/page", "http://docs.example.com/page"),
  ],
)
async def test_every_destination_is_checked_as_an_absolute_url(monkeypatch, given, checked):
  seen: list = []
  monkeypatch.setattr(ex, "validate_mcp_endpoint_url", lambda url, resolve_dns=True: seen.append((url, resolve_dns)) or True)
  result = await IntegrationToolExecutor().execute_mcp_tool(server_for(NAVIGATE), NAVIGATE, {"url": given})
  assert "transport is not enabled" in result["error"]
  assert seen == [(checked, True)]


@pytest.mark.asyncio
async def test_a_write_tool_asks_for_confirmation_when_the_caller_says_nothing(audit):
  server = server_for(NAVIGATE, read_only=False)
  result = await IntegrationToolExecutor().execute_mcp_tool(server, NAVIGATE, {"url": "https://docs.example.com"})
  assert result["requires_confirmation"] is True
