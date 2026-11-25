"""Administrators decide which domains the tools of an MCP server may be pointed at."""

from __future__ import annotations

import pytest

from app.db.repositories.mcp_server_repository import McpServerRepository
from tests.test_api_mcp_servers import admin, regular, repo  # noqa: F401  (fixtures)
from tests.test_db_async_repositories import session  # noqa: F401  (fixture)


def create(client, url="https://mcp.example.com"):
  return client.post("/api/mcp-servers", json={"name": "Playwright", "endpoint_url": url}).json()["id"]


def test_a_new_server_allows_no_domain(admin):  # noqa: F811
  r = admin.post("/api/mcp-servers", json={"name": "s", "endpoint_url": "https://mcp.example.com"})
  assert r.json()["allowed_domains"] == []


def test_an_administrator_sets_the_allowed_domains(admin, repo):  # noqa: F811
  sid = create(admin)
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"allowed_domains": ["Docs.Example.com", "docs.example.com", "wiki.example.org"]})
  assert r.status_code == 200 and r.json()["allowed_domains"] == ["docs.example.com", "wiki.example.org"]
  assert admin.get("/api/mcp-servers").json()[0]["allowed_domains"] == ["docs.example.com", "wiki.example.org"]


@pytest.mark.parametrize("bad", [["https://example.com"], ["*.example.com"], ["localhost"], ["example.com/path"], ["10.0.0.1"], [""]])
def test_only_bare_host_names_are_accepted(admin, bad):  # noqa: F811
  sid = create(admin)
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"allowed_domains": bad})
  assert r.status_code == 400 and "not a valid domain" in r.json()["detail"]


def test_renaming_a_server_keeps_its_domains(admin):  # noqa: F811
  sid = create(admin)
  admin.patch(f"/api/mcp-servers/{sid}", json={"allowed_domains": ["docs.example.com"]})
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"name": "renamed"})
  assert r.json()["allowed_domains"] == ["docs.example.com"]


def test_changing_the_endpoint_clears_the_domains_and_the_approvals(admin):  # noqa: F811
  sid = create(admin)
  admin.patch(f"/api/mcp-servers/{sid}", json={"allowed_domains": ["docs.example.com"]})
  admin.put(f"/api/mcp-servers/{sid}/tools", json=[{"name": "navigate", "read_only": False}])
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"endpoint_url": "https://other.example.com"})
  assert r.json()["allowed_domains"] == [] and r.json()["tools"] == []


def test_the_endpoint_change_can_set_new_domains_in_the_same_request(admin):  # noqa: F811
  sid = create(admin)
  r = admin.patch(f"/api/mcp-servers/{sid}", json={"endpoint_url": "https://other.example.com", "allowed_domains": ["a.example.com"]})
  assert r.json()["allowed_domains"] == ["a.example.com"]


def test_regular_users_cannot_change_the_domains(regular):  # noqa: F811
  assert regular.patch("/api/mcp-servers/srv-1", json={"allowed_domains": ["a.example.com"]}).status_code == 403


@pytest.mark.asyncio
async def test_the_repository_stores_domains_next_to_other_metadata(session):  # noqa: F811
  repo_ = McpServerRepository(session)
  server = await repo_.create("u1", "s", "http://x")
  assert server["allowed_domains"] == []
  updated = await repo_.update(server["id"], None, {"allowed_domains": ["B.example.com", "a.example.com"]})
  assert updated["allowed_domains"] == ["b.example.com", "a.example.com"]
  assert (await repo_.get_by_id(server["id"]))["allowed_domains"] == ["b.example.com", "a.example.com"]
  # unrelated updates leave them alone, and so do approvals
  assert (await repo_.update(server["id"], None, {"name": "n"}))["allowed_domains"] == ["b.example.com", "a.example.com"]
  assert (await repo_.update(server["id"], None, {"tools": []}))["allowed_domains"] == ["b.example.com", "a.example.com"]
  assert (await repo_.update(server["id"], None, {"allowed_domains": []}))["allowed_domains"] == []
  with pytest.raises(ValueError):
    await repo_.update(server["id"], None, {"allowed_domains": ["https://bad"]})
