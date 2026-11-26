"""SSRF guard of the MCP endpoints: which addresses and URLs are refused, and how redirects are followed."""

from __future__ import annotations

import ipaddress
import socket

import httpx
import pytest

from app.integrations import executor as ex


@pytest.mark.parametrize(
  "address",
  [
    "127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.1.1", "169.254.169.254", "224.0.0.1", "240.0.0.1", "0.0.0.0",
    "100.64.0.1", "100.100.5.5", "100.127.255.254", "::1", "fe80::1", "fc00::1", "ff02::1", "::",
  ],
)
def test_internal_and_reserved_addresses_are_refused(address):
  assert ex.validate_mcp_ip_address(ipaddress.ip_address(address)) is False


@pytest.mark.parametrize("address", ["8.8.8.8", "93.184.216.34", "100.63.255.255", "100.128.0.1", "2606:4700::1111"])
def test_public_addresses_are_accepted(address):
  assert ex.validate_mcp_ip_address(ipaddress.ip_address(address)) is True


@pytest.mark.parametrize(
  "url",
  [
    "http://localhost:8080/sse",
    "http://LOCALHOST/sse",
    "http://127.0.0.1/sse",
    "http://0.0.0.0/sse",
    "http://[::1]/sse",
    "http://10.0.0.1/mcp",
    "http://169.254.169.254/latest/meta-data",
    "http://metadata.google.internal/computeMetadata",
    "http://instance-data/latest",
    "http://printer.local/mcp",
    "http://Printer.LOCAL/mcp",
    "ftp://example.com/server",
    "file:///etc/passwd",
    "example.com/no-scheme",
    "https:///no-host",
    "http://external.com:22/sse",
    "https://external.com:99999/sse",
    "",
    "   ",
    None,
    42,
  ],
)
def test_unsafe_or_malformed_endpoints_are_refused(url):
  assert ex.validate_mcp_endpoint_url(url, resolve_dns=False) is False


@pytest.mark.parametrize(
  ("url", "port"),
  [
    ("https://mcp.example.com/sse", 443),
    ("HTTPS://mcp.example.com/sse", 443),
    ("http://mcp.example.com/sse", 80),
    ("  https://mcp.example.com/sse  ", 443),
    ("http://mcp.example.com:8080/sse", 8080),
    ("https://mcp.example.com:8443/sse", 8443),
    ("https://8.8.8.8/sse", 443),
    ("https://localhost.example.com/sse", 443),
  ],
)
def test_public_endpoints_are_accepted(url, port):
  assert ex.validate_mcp_endpoint_url(url, resolve_dns=False) is True


def test_a_raw_private_ip_is_refused_even_when_dns_is_skipped():
  assert ex.validate_mcp_endpoint_url("https://192.168.0.7/sse", resolve_dns=False) is False


def _resolving_to(monkeypatch, *addresses):
  seen = []

  def fake_getaddrinfo(host, port, family, kind):
    seen.append((host, port, family, kind))
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses]

  monkeypatch.setattr(ex.socket, "getaddrinfo", fake_getaddrinfo)
  return seen


def test_a_domain_that_resolves_to_public_addresses_is_accepted(monkeypatch):
  seen = _resolving_to(monkeypatch, "93.184.216.34", "8.8.8.8")
  assert ex.validate_mcp_endpoint_url("https://mcp.example.com/sse") is True
  assert seen == [("mcp.example.com", 443, socket.AF_UNSPEC, socket.SOCK_STREAM)]


def test_the_resolution_uses_the_port_of_the_url(monkeypatch):
  seen = _resolving_to(monkeypatch, "93.184.216.34")
  ex.validate_mcp_endpoint_url("http://mcp.example.com:8080/sse")
  assert seen[0][1] == 8080


def test_a_domain_with_any_private_record_is_refused(monkeypatch):
  _resolving_to(monkeypatch, "93.184.216.34", "10.0.0.5")
  assert ex.validate_mcp_endpoint_url("https://mcp.example.com/sse") is False


def test_a_domain_that_does_not_resolve_is_refused(monkeypatch):
  def unresolvable(*args):
    raise socket.gaierror("no such host")

  monkeypatch.setattr(ex.socket, "getaddrinfo", unresolvable)
  assert ex.validate_mcp_endpoint_url("https://nowhere.example.com/sse") is False


def test_an_unreadable_resolution_is_refused(monkeypatch):
  monkeypatch.setattr(ex.socket, "getaddrinfo", lambda *a: [(socket.AF_INET6, 1, 6, "", ("fe80::1%eth0", 443, 0, 0))])
  assert ex.validate_mcp_endpoint_url("https://mcp.example.com/sse") is False


def test_dns_is_not_resolved_when_not_asked(monkeypatch):
  def boom(*args):
    raise AssertionError("must not resolve")

  monkeypatch.setattr(ex.socket, "getaddrinfo", boom)
  assert ex.validate_mcp_endpoint_url("https://mcp.example.com/sse", resolve_dns=False) is True


def test_dns_is_resolved_by_default(monkeypatch):
  _resolving_to(monkeypatch, "127.0.0.1")
  assert ex.validate_mcp_endpoint_url("https://rebind.example.com/sse") is False


class _Transport:
  """Stands in for the network: records the requests and answers with a fixed response."""

  def __init__(self, response: httpx.Response):
    self.response = response
    self.requests: list[httpx.Request] = []

  def handler(self, request: httpx.Request) -> httpx.Response:
    self.requests.append(request)
    return self.response


@pytest.fixture
def network(monkeypatch):
  """Lets every host pass the guard and routes httpx through a recorded transport."""
  holder: dict = {}
  real_client = httpx.AsyncClient

  def make_client(**kwargs):
    holder["kwargs"] = kwargs
    return real_client(transport=httpx.MockTransport(holder["transport"].handler), **kwargs)

  monkeypatch.setattr(ex.httpx, "AsyncClient", make_client)
  monkeypatch.setattr(ex, "validate_mcp_endpoint_url", lambda url, resolve_dns=True: "evil" not in url)

  def arm(response: httpx.Response) -> _Transport:
    holder["transport"] = _Transport(response)
    return holder["transport"]

  arm.holder = holder
  return arm


@pytest.mark.asyncio
async def test_post_sends_the_payload_without_following_redirects(network):
  transport = network(httpx.Response(200, json={"ok": True}))
  response = await ex.SafeMCPHttpClient(timeout=3.0).post(
    "https://mcp.example.com/rpc", {"jsonrpc": "2.0"}, headers={"X-Test": "1"}
  )
  assert response.json() == {"ok": True}
  request = transport.requests[0]
  assert request.url == "https://mcp.example.com/rpc"
  assert request.headers["X-Test"] == "1"
  assert request.content == b'{"jsonrpc":"2.0"}'
  assert network.holder["kwargs"] == {"timeout": 3.0, "follow_redirects": False}


@pytest.mark.asyncio
async def test_post_has_a_default_timeout(network):
  network(httpx.Response(200))
  await ex.SafeMCPHttpClient().post("https://mcp.example.com/rpc", {})
  assert network.holder["kwargs"]["timeout"] == 15.0


@pytest.mark.asyncio
async def test_post_refuses_an_unsafe_endpoint_before_connecting(network):
  transport = network(httpx.Response(200))
  with pytest.raises(ValueError, match=r"Endpoint 'https://evil.example.com/rpc' rejected by SSRF security policy"):
    await ex.SafeMCPHttpClient().post("https://evil.example.com/rpc", {})
  assert transport.requests == []


@pytest.mark.asyncio
async def test_post_returns_a_redirect_to_a_safe_target(network):
  network(httpx.Response(302, headers={"Location": "https://mcp.example.com/other"}))
  response = await ex.SafeMCPHttpClient().post("https://mcp.example.com/rpc", {})
  assert response.status_code == 302


@pytest.mark.asyncio
async def test_post_refuses_a_redirect_into_an_unsafe_target(network):
  network(httpx.Response(302, headers={"Location": "https://evil.example.com/steal"}))
  with pytest.raises(ValueError, match=r"Redirect target 'https://evil.example.com/steal' is not permitted"):
    await ex.SafeMCPHttpClient().post("https://mcp.example.com/rpc", {})


@pytest.mark.asyncio
async def test_post_refuses_a_redirect_without_a_location(network):
  network(httpx.Response(302))
  with pytest.raises(ValueError, match="Redirect target 'None' is not permitted"):
    await ex.SafeMCPHttpClient().post("https://mcp.example.com/rpc", {})
