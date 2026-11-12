"""Pruebas unitarias para los nuevos repositorios del Repository Pattern."""

import pytest
from app.db.repositories.integration_repository import IntegrationRepository
from app.db.repositories.mcp_server_repository import McpServerRepository
from app.db.repositories.organization_repository import OrganizationRepository
from app.db.repositories.secret_repository import UserSecretRepository
from app.db.repositories.settings_repository import SettingsRepository
from app.db.unit_of_work import AsyncUnitOfWork, SyncUnitOfWork
from tests.fake_session import FakeAsyncSession, FakeStorage, FakeSyncSession


@pytest.fixture
def fake_storage():
  return FakeStorage()


@pytest.mark.asyncio
async def test_mcp_server_repository_crud(fake_storage):
  session = FakeAsyncSession(fake_storage)
  repo = McpServerRepository(session)

  # Create
  server = await repo.create(
    user_id="user-123",
    name="Test Server",
    endpoint_url="http://localhost:8080/sse",
    description="Test description",
    transport_type="sse",
    auth_type="bearer",
    allowed_tools=["fetch", "ping"],
  )
  assert server["id"] is not None
  assert server["name"] == "Test Server"
  assert server["allowed_tools"] == ["fetch", "ping"]

  # List
  servers = await repo.list_by_user("user-123")
  assert len(servers) == 1
  assert servers[0]["id"] == server["id"]

  # Update
  updated = await repo.update(server["id"], "user-123", {"name": "Updated Server", "status": "active"})
  assert updated["name"] == "Updated Server"
  assert updated["status"] == "active"

  # Update status
  status_updated = await repo.update_status(server["id"], "user-123", "connected")
  assert status_updated["status"] == "connected"

  # Delete
  deleted = await repo.delete(server["id"], "user-123")
  assert deleted is True

  # Verify deletion
  remaining = await repo.list_by_user("user-123")
  assert len(remaining) == 0


def test_user_secret_repository_crud(fake_storage):
  session = FakeSyncSession(fake_storage)
  repo = UserSecretRepository(session)

  # Create secret
  secret = repo.create(
    secret_id="sec-1",
    user_id="user-123",
    purpose="test_purpose",
    ciphertext="base64cipher",
    nonce="base64nonce",
    key_version=1,
  )
  assert secret["id"] == "sec-1"
  assert secret["user_id"] == "user-123"

  # Get by id
  fetched = repo.get_by_id("sec-1")
  assert fetched is not None
  assert fetched["ciphertext"] == "base64cipher"

  # Update ciphertext
  updated = repo.update_ciphertext(
    secret_id="sec-1",
    user_id="user-123",
    ciphertext="newciphertext",
    nonce="newnonce",
    key_version=2,
  )
  assert updated["ciphertext"] == "newciphertext"
  assert updated["key_version"] == 2

  # Delete
  deleted = repo.delete("sec-1", "user-123")
  assert deleted is True
  assert repo.get_by_id("sec-1") is None


def test_settings_repository_crud(fake_storage):
  session = FakeSyncSession(fake_storage)
  repo = SettingsRepository(session)

  # Set and get setting
  repo.set_setting("app_theme", '"dark"')
  val = repo.get_setting("app_theme")
  assert val == '"dark"'

  all_settings = repo.get_all_settings()
  assert all_settings.get("app_theme") == '"dark"'

  # User preferences
  prefs = repo.save_user_preferences("user-123", {
    "inference_provider": "gemini",
    "inference_model": "gemini-1.5-pro",
    "custom_color": "blue",
  })
  assert prefs["inference_provider"] == "gemini"
  assert prefs["custom_color"] == "blue"

  loaded = repo.get_user_preferences("user-123")
  assert loaded["inference_model"] == "gemini-1.5-pro"


def test_integration_repository_crud(fake_storage):
  session = FakeSyncSession(fake_storage)
  repo = IntegrationRepository(session)

  # Save user credential
  repo.save_user_credential(
    user_id="user-123",
    provider="openai",
    secret_id="sec-openai",
    secret_ref="sec::sec-openai",
  )
  cred = repo.get_user_credential("user-123", "openai")
  assert cred is not None
  assert cred["secret_id"] == "sec-openai"

  creds_list = repo.list_user_credentials("user-123")
  assert len(creds_list) == 1
  assert creds_list[0]["provider"] == "openai"

  # Delete user credential
  deleted = repo.delete_user_credential("user-123", "openai")
  assert deleted is True
  assert repo.get_user_credential("user-123", "openai") is None

  # Organization integration
  repo.save_organization_integration(
    organization_id="org-1",
    provider="jira",
    client_id="jira-client-id",
    client_secret_ref="jira-secret-ref",
  )
  assert repo.organization_integration_exists("org-1", "jira") is True

  org_int = repo.get_organization_integration("org-1", "jira")
  assert org_int["client_id"] == "jira-client-id"

  deleted_org = repo.delete_organization_integration("org-1", "jira")
  assert deleted_org is True
  assert repo.organization_integration_exists("org-1", "jira") is False


@pytest.mark.asyncio
async def test_organization_repository_crud(fake_storage):
  session = FakeAsyncSession(fake_storage)
  repo = OrganizationRepository(session)

  org = await repo.create_organization("Acme Corp", "acme")
  assert org["name"] == "Acme Corp"
  assert org["slug"] == "acme"

  by_slug = await repo.get_by_slug("acme")
  assert by_slug is not None
  assert by_slug["id"] == org["id"]

  member = await repo.add_member(org["id"], "user-123", "admin")
  assert member["role"] == "admin"

  members = await repo.list_members(org["id"])
  assert len(members) == 1

  updated_member = await repo.update_member_role(org["id"], "user-123", "viewer")
  assert updated_member["role"] == "viewer"

  removed = await repo.remove_member(org["id"], "user-123")
  assert removed is True
  assert await repo.get_member(org["id"], "user-123") is None


@pytest.mark.asyncio
async def test_unit_of_work_transaction(fake_storage):
  session = FakeAsyncSession(fake_storage)
  uow = AsyncUnitOfWork(session_factory=lambda: session)

  async with uow:
    server = await uow.mcp_servers.create(
      user_id="user-uow",
      name="UoW Server",
      endpoint_url="http://localhost:9000",
    )
    assert server["name"] == "UoW Server"
    await uow.commit()

  sync_session = FakeSyncSession(fake_storage)
  sync_uow = SyncUnitOfWork(session_factory=lambda: sync_session)
  with sync_uow:
    sync_uow.settings.set_setting("sync_key", '"sync_val"')
    sync_uow.commit()

  assert sync_uow.settings.get_setting("sync_key") == '"sync_val"'
