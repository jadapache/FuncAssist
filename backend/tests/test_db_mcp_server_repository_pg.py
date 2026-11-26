"""McpServerRepository against a real PostgreSQL: which rows a user or an administrator can reach."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.db.models import UserModel
from app.db.repositories.mcp_server_repository import McpServerRepository

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def repo(pg_async_session):
  pg_async_session.add_all([UserModel(id="u1", username="ana"), UserModel(id="u2", username="bob")])
  await pg_async_session.flush()
  return McpServerRepository(pg_async_session)


async def test_a_user_reaches_only_the_servers_they_registered(repo):
  mine = await repo.create("u1", "mine", "https://a.example.com")
  theirs = await repo.create("u2", "theirs", "https://b.example.com")
  assert (await repo.get_by_id(mine["id"], user_id="u1"))["name"] == "mine"
  assert await repo.get_by_id(mine["id"], user_id="u2") is None
  assert await repo.get_by_id("missing", user_id="u1") is None
  assert (await repo.get_by_id(theirs["id"]))["name"] == "theirs"


async def test_listing_by_user_returns_only_their_servers(repo):
  await repo.create("u1", "one", "https://a.example.com")
  await repo.create("u1", "two", "https://b.example.com")
  await repo.create("u2", "other", "https://c.example.com")
  assert sorted(s["name"] for s in await repo.list_by_user("u1")) == ["one", "two"]
  assert [s["name"] for s in await repo.list_by_user("u2")] == ["other"]
  assert await repo.list_by_user("nobody") == []
  assert len(await repo.list_all()) == 3


async def test_a_user_cannot_update_or_delete_a_server_of_someone_else(repo):
  server = await repo.create("u1", "mine", "https://a.example.com")
  assert await repo.update(server["id"], "u2", {"name": "hijacked"}) is None
  assert await repo.delete(server["id"], "u2") is False
  assert (await repo.get_by_id(server["id"]))["name"] == "mine"
  assert (await repo.update(server["id"], "u1", {"name": "renamed"}))["name"] == "renamed"
  assert await repo.delete(server["id"], "u1") is True
  assert await repo.get_by_id(server["id"]) is None


async def test_an_administrator_without_a_user_filter_reaches_every_server(repo):
  server = await repo.create("u1", "mine", "https://a.example.com")
  assert (await repo.update(server["id"], None, {"status": "connected"}))["status"] == "connected"
  assert (await repo.update_status(server["id"], None, "error"))["status"] == "error"
  assert await repo.delete(server["id"]) is True


async def test_an_update_changes_only_the_fields_given(repo):
  server = await repo.create("u1", "mine", "https://a.example.com", description="d", transport_type="sse", auth_type="none")
  updated = await repo.update(server["id"], None, {
    "name": " new ", "description": None, "endpoint_url": " https://b.example.com ", "transport_type": "http",
    "auth_type": "bearer", "status": "connected",
  })
  assert (updated["name"], updated["description"], updated["endpoint_url"]) == ("new", "d", "https://b.example.com")
  assert (updated["transport_type"], updated["auth_type"], updated["status"]) == ("http", "bearer", "connected")
  assert updated["tools"] == [] and updated["allowed_domains"] == []
