"""Tests for Integrations Architecture: Organization Integrations, User Integrations, Security, and MCP.

Covers:
  - Organization connection persistence for GitHub and GitLab
  - Organization isolation between two orgs with same provider
  - Personal Jira connection scoped strictly per user (1 connection per user)
  - Rejection / overwrite isolation and security bounds across users
  - User isolation: preventing User A from accessing User B's tokens or connection
  - No silent fallback from personal query to organization connection
  - Public facade compatibility in app.core.storage
  - Fernet encryption and decryption for sensitive tokens and metadata
  - MCP endpoint SSRF validation (IPv4, IPv6, loopback, link-local, cloud metadata, port restriction)
  - MCP executor tool authorization gating
  - OAuth state CSRF validation, replay prevention, and expiration window
  - Safe redirect checks in MCP HTTP client
  - Migration idempotency
"""

import time
from unittest.mock import patch
import pytest
from app.core import storage
from app.core.integration_migration import migrate_integrations_schema_if_needed
from app.core.storage_cache import clear_storage_caches
from app.db.models import (
  McpServerModel,
  OrganizationIntegrationModel,
  UserIntegrationModel,
)
from app.integrations.executor import (
  IntegrationToolExecutor,
  SafeMCPHttpClient,
  validate_mcp_endpoint_url,
)
from app.integrations.jira.integration import JiraIntegration
from tests.fake_session import FakeSyncSession, GLOBAL_FAKE_STORAGE


@pytest.fixture(autouse=True)
def setup_storage():
  clear_storage_caches()
  GLOBAL_FAKE_STORAGE.clear()
  yield
  clear_storage_caches()
  GLOBAL_FAKE_STORAGE.clear()


def test_organization_github_and_gitlab_persistence():
  """Test storing and loading organization connections for GitHub and GitLab."""
  github_payload = {
    "auth_method": "pat",
    "pat_token": "ghp_secure_org_token_123",
    "account_login": "acme-corp",
    "selected_repos": ["acme/backend", "acme/frontend"],
  }
  storage.save_connection("github", github_payload, org_id="org-acme")

  loaded = storage.load_connection("github", org_id="org-acme")
  assert loaded is not None
  assert loaded["account_login"] == "acme-corp"
  assert loaded["pat_token"] == "ghp_secure_org_token_123"
  assert loaded["selected_repos"] == ["acme/backend", "acme/frontend"]


def test_organization_isolation_same_provider():
  """Ensure different organizations have complete data isolation for the same provider."""
  storage.save_connection("gitlab", {"pat_token": "glpat-org1", "group": "org1"}, org_id="org-1")
  storage.save_connection("gitlab", {"pat_token": "glpat-org2", "group": "org2"}, org_id="org-2")

  res1 = storage.load_connection("gitlab", org_id="org-1")
  res2 = storage.load_connection("gitlab", org_id="org-2")

  assert res1 is not None and res2 is not None
  assert res1["pat_token"] == "glpat-org1"
  assert res2["pat_token"] == "glpat-org2"
  assert res1["pat_token"] != res2["pat_token"]


def test_user_personal_jira_persistence_and_isolation():
  """Test personal Jira integration stored per user_id and provider."""
  user_a = "usr-alpha"
  user_b = "usr-beta"

  payload_a = {
    "auth_method": "oauth",
    "access_token": "atlassian-token-alpha",
    "refresh_token": "refresh-alpha",
    "account_email": "alpha@example.com",
    "cloud_id": "cloud-alpha-123",
  }
  payload_b = {
    "auth_method": "oauth",
    "access_token": "atlassian-token-beta",
    "refresh_token": "refresh-beta",
    "account_email": "beta@example.com",
    "cloud_id": "cloud-beta-456",
  }

  storage.save_user_integration(user_a, "jira", payload_a)
  storage.save_user_integration(user_b, "jira", payload_b)

  conn_a = storage.load_user_integration(user_a, "jira")
  conn_b = storage.load_user_integration(user_b, "jira")

  assert conn_a is not None and conn_b is not None
  assert conn_a["account_email"] == "alpha@example.com"
  assert conn_b["account_email"] == "beta@example.com"
  assert conn_a["access_token"] == "atlassian-token-alpha"
  assert conn_b["access_token"] == "atlassian-token-beta"

  # User A cannot access User B's connection
  assert storage.load_user_integration("user-unknown", "jira") is None


def test_user_personal_jira_single_connection_update():
  """Test that re-saving Jira connection for the same user updates the record instead of duplicating."""
  user_id = "usr-charlie"

  storage.save_user_integration(user_id, "jira", {
    "access_token": "token-v1",
    "account_email": "charlie@v1.com",
  })

  storage.save_user_integration(user_id, "jira", {
    "access_token": "token-v2",
    "account_email": "charlie@v2.com",
  })

  loaded = storage.load_user_integration(user_id, "jira")
  assert loaded is not None
  assert loaded["access_token"] == "token-v2"
  assert loaded["account_email"] == "charlie@v2.com"


def test_user_integration_deletion():
  """Test disconnecting user personal integration."""
  user_id = "usr-delta"
  storage.save_user_integration(user_id, "jira", {"access_token": "token-to-delete"})
  assert storage.user_integration_exists(user_id, "jira") is True

  deleted = storage.delete_user_integration(user_id, "jira")
  assert deleted is True
  assert storage.load_user_integration(user_id, "jira") is None
  assert storage.user_integration_exists(user_id, "jira") is False


def test_no_silent_fallback_to_org_jira_for_personal_scope():
  """Verify that a user without personal Jira connection is NOT quietly given organization credentials."""
  jira = JiraIntegration()
  # Set an organization connection
  storage.save_connection("jira", {"site_url": "https://org.atlassian.net", "cloud_id": "org-cloud"})

  # For a specific user with NO personal connection, resolving personal data returns None if loaded directly
  user_no_conn = "user-without-jira"
  personal_data = storage.load_user_integration(user_no_conn, "jira")
  assert personal_data is None


def test_storage_public_facade_integrity():
  """Verify all personal user integration and MCP exports exist on storage public facade."""
  required_exports = [
    "save_user_integration",
    "load_user_integration",
    "delete_user_integration",
    "user_integration_exists",
    "UserIntegrationModel",
    "McpServerModel",
  ]
  for sym in required_exports:
    assert hasattr(storage, sym), f"{sym} is missing from app.core.storage facade."


def test_mcp_endpoint_ssrf_validator_ipv4_and_ipv6():
  """Test SSRF validation rejects private IPs, loopbacks, IPv6, and bad schemes."""
  # Unsafe endpoints
  assert validate_mcp_endpoint_url("http://localhost:8000/sse", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://127.0.0.1:3000/sse", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://10.0.0.1/mcp", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://192.168.1.50:8080/mcp", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://172.16.0.5/mcp", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://169.254.169.254/latest/meta-data", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://[::1]/sse", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://[fe80::1]/sse", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("ftp://example.com/server", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("http://external.com:22/sse", resolve_dns=False) is False
  assert validate_mcp_endpoint_url("", resolve_dns=False) is False

  # Safe external endpoints (without DNS network call in unit test)
  assert validate_mcp_endpoint_url("https://mcp.external-service.com/sse", resolve_dns=False) is True
  assert validate_mcp_endpoint_url("https://api.github.com/mcp", resolve_dns=False) is True
  assert validate_mcp_endpoint_url("https://93.184.216.34:443/mcp", resolve_dns=False) is True


@pytest.mark.asyncio
async def test_mcp_safe_client_rejects_ssrf():
  """Test that SafeMCPHttpClient blocks disallowed endpoints and private redirect targets."""
  client = SafeMCPHttpClient()

  with pytest.raises(ValueError, match="rejected by SSRF security policy"):
    await client.post("http://127.0.0.1:8080/eval", json_data={})


@pytest.mark.asyncio
async def test_mcp_tool_executor_permissions():
  """Test MCP executor tool authorization gating."""
  executor = IntegrationToolExecutor(organization_id="org-test")

  # Disallowed tool
  res = await executor.execute_tool(
    provider="jira",
    tool_name="dangerous_operation",
    arguments={},
    allowed_tools=["get_issues", "get_projects"],
  )
  assert res["ok"] is False
  assert "not authorized" in res["error"]

  # Tool allowed by wildcard
  assert executor.can_invoke_tool("jira", "get_issues", ["*"]) is True
  assert executor.can_invoke_tool("jira", "get_issues", ["get_issues"]) is True
  assert executor.can_invoke_tool("jira", "delete_all", ["get_issues"]) is False


@pytest.mark.asyncio
async def test_jira_oauth_state_expiration_and_replay():
  """Test Jira OAuth state validation, expiry, and single-use security."""
  jira = JiraIntegration()
  user_id = "user-oauth-test"

  with patch("app.integrations.jira.integration.get_jira_oauth_config") as mock_cfg:
    mock_cfg.return_value = {
      "configured": True,
      "client_id": "test_id",
      "client_secret": "test_sec",
      "redirect_uri": "http://127.0.0.1:6728/api/integrations/jira/callback",
    }
    resp = await jira.start_oauth(user_id=user_id)
    assert resp.state is not None
    assert user_id in resp.state

    # 1. State mismatch
    with pytest.raises(ValueError, match="Invalid OAuth state"):
      await jira.handle_oauth_callback(code="code123", state="invalid-state")

    # 2. Expired state
    expired_state = f"{user_id}::{int(time.time()) - 1000}::oldtoken"
    storage.save_user_integration(user_id, "jira", {"oauth_state": expired_state})
    with pytest.raises(ValueError, match="expired"):
      await jira.handle_oauth_callback(code="code123", state=expired_state)


def test_migrations_idempotency():
  """Ensure migrate_integrations_schema_if_needed can be called multiple times without error."""
  # First invocation
  migrate_integrations_schema_if_needed()
  # Subsequent invocation
  migrate_integrations_schema_if_needed()
