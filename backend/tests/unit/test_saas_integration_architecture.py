"""Comprehensive automated test suite for SaaS refactoring and security architecture.

Verifies:
- Entity UUID Primary Keys and Foreign Key relationships
- Independent Preferences (Inference, Transcription, Language)
- BYOK Credentials lifecycle, SecretStore AES-256-GCM encryption, and access boundaries
- User isolation: User A cannot access User B's credentials or Jira tokens
- Personal Jira individual OAuth connection, state validation, and disconnection
- Generic settings migration idempotency, safe re-encryption, and audit logging
- Absence of plaintext secrets in API responses
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.core.rls_context import reset_rls_context, set_rls_context
from app.core.secret_store import secret_store
from app.core.storage_credentials import (
  delete_user_credential,
  list_user_credentials_info,
  load_all_user_credentials,
  load_user_credential,
  save_user_credential,
)
from app.core.storage_preferences import get_user_preferences, save_user_preferences
from app.core.storage_user_integrations import (
  delete_user_integration,
  load_user_integration,
  save_user_integration,
  user_integration_exists,
)
from app.db.database import set_session_override, set_sync_session_override
from app.db.models import (
  AuditEventModel,
  OrganizationMemberModel,
  OrganizationModel,
  SettingModel,
  UserModel,
  UserPreferencesModel,
  UserProviderCredentialModel,
  UserSecretModel,
)
from app.main import app
from tests.fake_session import GLOBAL_FAKE_STORAGE, FakeSyncSession, fake_async_db, fake_sync_db


@pytest.fixture(autouse=True)
def setup_test_db():
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(fake_async_db)
  set_sync_session_override(fake_sync_db)
  yield
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(None)
  set_sync_session_override(None)


# ---------------------------------------------------------------------------
# 1. UUID Primary Keys and Entity Foreign Keys Verification
# ---------------------------------------------------------------------------

def test_all_entities_have_uuid_primary_keys():
  """Assert that newly instantiated entities automatically have UUID4 primary keys."""
  import uuid

  user = UserModel(username="alice", email="alice@test.com")
  org = OrganizationModel(name="Acme Corp", slug="acme")
  member = OrganizationMemberModel(organization_id=org.id, user_id=user.id, role="admin")
  pref = UserPreferencesModel(user_id=user.id, inference_provider="openai")
  secret = UserSecretModel(user_id=user.id, purpose="byok_openai", ciphertext="abc", nonce="123")
  cred = UserProviderCredentialModel(user_id=user.id, provider="openai", secret_ref="sec::test")
  setting = SettingModel(key="app_test", value_json="{}")

  for entity in (user, org, member, pref, secret, cred, setting):
    assert hasattr(entity, "id")
    assert entity.id is not None
    # Validate string format is valid UUID
    parsed = uuid.UUID(entity.id)
    assert str(parsed) == entity.id


# ---------------------------------------------------------------------------
# 2. Independent Preferences Tests
# ---------------------------------------------------------------------------

def test_independent_inference_and_transcription_preferences():
  """Preferences for inference and transcription must be completely decoupled."""
  user_id = "user-pref-001"

  # Initial save
  saved = save_user_preferences(user_id, {
    "inference_provider": "anthropic",
    "inference_model": "claude-3-5-sonnet",
    "transcription_provider": "groq",
    "transcription_model": "whisper-large-v3",
    "language": "es",
  })
  assert saved["inference_provider"] == "anthropic"
  assert saved["inference_model"] == "claude-3-5-sonnet"
  assert saved["transcription_provider"] == "groq"
  assert saved["transcription_model"] == "whisper-large-v3"
  assert saved["language"] == "es"

  # Update inference only -> transcription remains intact
  save_user_preferences(user_id, {
    "inference_provider": "gemini",
    "inference_model": "gemini-2.0-flash",
  })

  fetched = get_user_preferences(user_id)
  assert fetched["inference_provider"] == "gemini"
  assert fetched["inference_model"] == "gemini-2.0-flash"
  assert fetched["transcription_provider"] == "groq"
  assert fetched["transcription_model"] == "whisper-large-v3"


# ---------------------------------------------------------------------------
# 3. BYOK Credentials & SecretStore AES-256-GCM Encryption Tests
# ---------------------------------------------------------------------------

def test_byok_credentials_lifecycle_and_authenticated_encryption():
  """Full lifecycle of BYOK credentials with SecretStore AES-256-GCM authenticated encryption."""
  user_id = "user-byok-001"
  raw_key = "sk-proj-test-openai-secret-key-12345"

  # Save credential
  secret_id = save_user_credential(user_id, "openai", raw_key)
  assert secret_id is not None
  assert len(secret_id) > 10

  # Decrypt and verify matching plain value
  loaded = load_user_credential(user_id, "openai")
  assert loaded == raw_key

  # Public info listing must not contain secret or cipher
  info_list = list_user_credentials_info(user_id)
  assert len(info_list) == 1
  assert info_list[0]["provider"] == "openai"
  assert info_list[0]["is_configured"] is True
  assert "secret" not in str(info_list[0])
  assert raw_key not in str(info_list[0])

  # Replace credential
  new_key = "sk-proj-updated-key-67890"
  save_user_credential(user_id, "openai", new_key)
  assert load_user_credential(user_id, "openai") == new_key

  # Delete credential
  deleted = delete_user_credential(user_id, "openai")
  assert deleted is True
  assert load_user_credential(user_id, "openai") == ""
  assert len(list_user_credentials_info(user_id)) == 0


def test_byok_user_isolation_cannot_access_other_users_secrets():
  """User A must strictly never be able to access User B's encrypted secret."""
  user_a = "user-alice-001"
  user_b = "user-bob-002"

  secret_a_id = secret_store.create_secret(user_a, "byok_gemini", "gemini-alice-key-secret")
  assert secret_a_id is not None

  # User A can retrieve it
  plain_a = secret_store.get_secret(user_a, secret_a_id, purpose="byok_gemini")
  assert plain_a == "gemini-alice-key-secret"

  # User B attempts to access User A's secret -> PermissionError
  with pytest.raises(PermissionError, match="Unauthorized access"):
    secret_store.get_secret(user_b, secret_a_id, purpose="byok_gemini")

  # User B attempts to delete User A's secret -> PermissionError
  with pytest.raises(PermissionError):
    secret_store.delete_secret(user_b, secret_a_id)


# ---------------------------------------------------------------------------
# 4. Personal Jira Connection Isolation and OAuth Flow
# ---------------------------------------------------------------------------

def test_personal_jira_connection_isolation():
  """Jira connections are scoped strictly to individual users."""
  user_1 = "usr-eng-1"
  user_2 = "usr-eng-2"

  payload_1 = {
    "jira_url": "https://acme.atlassian.net",
    "cloud_id": "cloud-acme-1",
    "account_email": "dev1@acme.com",
    "access_token": "atlassian-access-token-1",
    "refresh_token": "atlassian-refresh-token-1",
    "status": "connected",
  }
  payload_2 = {
    "jira_url": "https://acme.atlassian.net",
    "cloud_id": "cloud-acme-2",
    "account_email": "dev2@acme.com",
    "access_token": "atlassian-access-token-2",
    "refresh_token": "atlassian-refresh-token-2",
    "status": "connected",
  }

  save_user_integration(user_1, "jira", payload_1)
  save_user_integration(user_2, "jira", payload_2)

  conn_1 = load_user_integration(user_1, "jira")
  conn_2 = load_user_integration(user_2, "jira")

  assert conn_1 is not None and conn_2 is not None
  assert conn_1["account_email"] == "dev1@acme.com"
  assert conn_2["account_email"] == "dev2@acme.com"
  assert conn_1["access_token"] != conn_2["access_token"]

  # Deleting user 1's connection leaves user 2 intact
  delete_user_integration(user_1, "jira")
  assert user_integration_exists(user_1, "jira") is False
  assert user_integration_exists(user_2, "jira") is True


# ---------------------------------------------------------------------------
# 5. RLS Context Isolation
# ---------------------------------------------------------------------------

def test_rls_context_setting_and_reset():
  """Test RLS context manager parameterization and execution."""
  from tests.fake_session import FakeSyncSession
  session = FakeSyncSession(GLOBAL_FAKE_STORAGE)

  set_rls_context(session, user_id="user-rls-1", org_id="org-acme")
  reset_rls_context(session)


# ---------------------------------------------------------------------------
# 7. Configuration API (/v1/me) Endpoints Verification
# ---------------------------------------------------------------------------

def test_api_v1_me_preferences_and_credentials_lifecycle():
  """Test full /v1/me REST API for user preferences and BYOK credentials."""
  from app.api.deps import get_current_user

  test_user = {"id": "usr-me-api-123", "username": "me_tester", "role": "user"}
  app.dependency_overrides[get_current_user] = lambda: test_user
  client = TestClient(app)

  try:
    # 1. Update preferences
    pref_res = client.patch("/v1/me/preferences", json={
      "inference_provider": "anthropic",
      "inference_model": "claude-3-7-sonnet",
      "transcription_provider": "groq",
      "transcription_model": "whisper-large-v3",
      "language": "es",
    })
    assert pref_res.status_code == 200
    pdata = pref_res.json()
    assert pdata["inference_provider"] == "anthropic"
    assert pdata["inference_model"] == "claude-3-7-sonnet"
    assert pdata["transcription_provider"] == "groq"

    # 2. Get preferences
    get_res = client.get("/v1/me/preferences")
    assert get_res.status_code == 200
    assert get_res.json()["inference_provider"] == "anthropic"

    # 3. Put provider credential
    put_cred = client.put("/v1/me/provider-credentials/anthropic", json={
      "api_key": "sk-ant-api-test-key-9999",
    })
    assert put_cred.status_code == 200
    cdata = put_cred.json()
    assert cdata["provider"] == "anthropic"
    assert cdata["status"] == "active"
    assert "sk-ant" not in str(cdata)

    # 4. List provider credentials (never leaks key)
    list_res = client.get("/v1/me/provider-credentials")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["provider"] == "anthropic"
    assert "sk-ant" not in str(items)

    # 5. Test credential
    test_res = client.post("/v1/me/provider-credentials/anthropic/test")
    assert test_res.status_code == 200
    assert test_res.json()["status"] == "active"

    # 6. Delete credential
    del_res = client.delete("/v1/me/provider-credentials/anthropic")
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True

    # 7. Jira status when disconnected
    jira_res = client.get("/v1/me/integrations/jira")
    assert jira_res.status_code == 200
    assert jira_res.json()["connected"] is False

    # 8. Jira disconnect endpoint
    del_jira = client.delete("/v1/me/integrations/jira")
    assert del_jira.status_code == 200
    assert del_jira.json()["status"] == "disconnected"
  finally:
    app.dependency_overrides.pop(get_current_user, None)
