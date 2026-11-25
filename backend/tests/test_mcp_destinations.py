"""Tools that navigate or fetch may only go where the administrator allowed, never into the internal network."""

from __future__ import annotations

import pytest

from app.integrations import executor as ex
from app.integrations import mcp_policy as policy
from app.integrations.mcp_policy import ToolDescriptor, approve_tool

NAVIGATE = ToolDescriptor(
  "browser_navigate", "Open a page",
  {"type": "object", "properties": {"url": {"type": "string"}, "note": {"type": "string"}}, "required": ["url"]},
)
SNAPSHOT = ToolDescriptor("snapshot", "Page snapshot", {"type": "object", "properties": {}})


# ----------------------------------------------------------------- pure helpers


@pytest.mark.parametrize("value,expected", [
  ("docs.example.com", "docs.example.com"), ("  Docs.Example.COM. ", "docs.example.com"), ("a-b.example.org", "a-b.example.org"),
])
def test_normalize_domain(value, expected):
  assert policy.normalize_domain(value) == expected


@pytest.mark.parametrize("value", [
  "", "localhost", "https://example.com", "example.com/path", "example.com:8080", "*.example.com",
  "-bad.example.com", "exa mple.com", "1.2.3.4", None, "a" * 300 + ".com",
])
def test_normalize_domain_rejects_everything_that_is_not_a_bare_host(value):
  with pytest.raises(ValueError, match="not a valid domain"):
    policy.normalize_domain(value)


def test_normalize_domains_deduplicates_and_keeps_order():
  assert policy.normalize_domains(["B.example.com", "a.example.com", "b.example.com"]) == ["b.example.com", "a.example.com"]
  assert policy.normalize_domains(None) == [] and policy.normalize_domains([]) == []


def test_extract_destinations_finds_urls_by_name_and_by_shape():
  args = {
    "url": "https://a.example.com/x",
    "note": "see https://b.example.com is not a bare url",  # prose is not a destination
    "options": {"href": "c.example.com", "items": [{"target": "d.example.com"}, "//e.example.com/p"]},
    "text": "hello", "to": "",
  }
  assert policy.extract_destinations(args) == [
    "https://a.example.com/x", "c.example.com", "d.example.com", "//e.example.com/p",
  ]
  assert policy.extract_destinations({"selector": "#id", "count": 3}) == []
  assert policy.extract_destinations("https://x.example.com") == []  # only argument objects are inspected


@pytest.mark.parametrize("value,host", [
  ("https://Docs.Example.com/path?q=1", "docs.example.com"),
  ("http://docs.example.com:8080/", "docs.example.com"),
  ("//docs.example.com/x", "docs.example.com"),
  ("docs.example.com", "docs.example.com"),
  ("https://docs.example.com./", "docs.example.com"),
])
def test_destination_host(value, host):
  assert policy.destination_host(value) == host


@pytest.mark.parametrize("value", ["javascript:alert(1)", "ftp://x.example.com", "file:///etc/passwd", "https://user:pw@x.example.com", "https://"])
def test_destination_host_rejects_other_schemes_credentials_and_empty_hosts(value):
  assert policy.destination_host(value) is None


@pytest.mark.parametrize("host,allowed,expected", [
  ("docs.example.com", ["docs.example.com"], True),
  ("a.docs.example.com", ["docs.example.com"], True),
  ("evildocs.example.com", ["docs.example.com"], False),
  ("docs.example.com.evil.io", ["docs.example.com"], False),
  ("example.com", ["docs.example.com"], False),
  ("docs.example.com", [], False),
])
def test_host_allowed_matches_domains_and_subdomains_only(host, allowed, expected):
  assert policy.host_allowed(host, allowed) is expected


def test_check_destinations():
  allowed = ["docs.example.com"]
  assert policy.check_destinations({"url": "https://docs.example.com/guide"}, allowed) == []
  assert policy.check_destinations({"selector": "#x"}, []) == []  # nothing to object to without a destination
  assert "not among the domains" in policy.check_destinations({"url": "https://evil.example/log?d=1"}, allowed)[0]
  assert "No destination is allowed" in policy.check_destinations({"url": "https://docs.example.com"}, [])[0]
  assert "No destination is allowed" in policy.check_destinations({"url": "https://docs.example.com"}, None)[0]
  assert "not an acceptable destination" in policy.check_destinations({"url": "javascript:alert(1)"}, allowed)[0]
  assert len(policy.check_destinations({"url": "https://a.evil.io", "href": "https://b.evil.io"}, allowed)) == 2


# ----------------------------------------------------------------- the executor applies them


def server(domains, *pairs):
  tools: list = []
  for descriptor, read_only in pairs:
    tools = approve_tool(tools, descriptor, read_only=read_only, approved_by="admin")
  return {"id": "srv-1", "name": "Playwright", "tools": tools, "allowed_domains": domains}


@pytest.fixture
def public_network(monkeypatch):
  seen: list = []
  monkeypatch.setattr(ex, "validate_mcp_endpoint_url", lambda url, resolve_dns=True: seen.append(url) or True)
  return seen


@pytest.mark.asyncio
async def test_an_allowed_destination_passes_the_policy(public_network):
  srv = server(["docs.example.com"], (NAVIGATE, True))
  res = await ex.IntegrationToolExecutor(user_id="u").execute_mcp_tool(srv, NAVIGATE, {"url": "https://docs.example.com/guide"})
  # authorized, but the transport is not enabled yet
  assert res["ok"] is False and "transport is not enabled" in res["error"]
  assert public_network == ["https://docs.example.com/guide"]


@pytest.mark.asyncio
@pytest.mark.parametrize("domains,url,message", [
  (["docs.example.com"], "https://evil.example/log?token=abc", "not among the domains"),
  ([], "https://docs.example.com", "No destination is allowed"),
  (None, "https://docs.example.com", "No destination is allowed"),
  (["docs.example.com"], "javascript:alert(1)", "not an acceptable destination"),
])
async def test_other_destinations_are_denied_before_anything_is_sent(public_network, domains, url, message):
  srv = server(domains, (NAVIGATE, True))
  res = await ex.IntegrationToolExecutor().execute_mcp_tool(srv, NAVIGATE, {"url": url})
  assert res["ok"] is False and res["error"].startswith("Destination not allowed") and message in res["error"]
  assert public_network == []


@pytest.mark.asyncio
async def test_an_allowed_domain_that_resolves_into_the_internal_network_is_denied(monkeypatch):
  monkeypatch.setattr(ex, "validate_mcp_endpoint_url", lambda url, resolve_dns=True: False)  # DNS points at 10.x
  srv = server(["docs.example.com"], (NAVIGATE, True))
  res = await ex.IntegrationToolExecutor().execute_mcp_tool(srv, NAVIGATE, {"url": "https://docs.example.com/guide"})
  assert res["ok"] is False and "private or unsafe address" in res["error"]


@pytest.mark.asyncio
async def test_tools_without_destinations_are_not_affected(public_network):
  srv = server([], (SNAPSHOT, True))
  res = await ex.IntegrationToolExecutor().execute_mcp_tool(srv, SNAPSHOT, {})
  assert "transport is not enabled" in res["error"] and public_network == []


@pytest.mark.asyncio
async def test_a_destination_hidden_in_another_argument_is_still_checked(public_network):
  srv = server(["docs.example.com"], (NAVIGATE, True))
  res = await ex.IntegrationToolExecutor().execute_mcp_tool(
    srv, NAVIGATE, {"url": "https://docs.example.com/", "note": "//evil.example/x"}
  )
  assert res["ok"] is False and "evil.example" in res["error"]
