"""Integrations: MCP endpoint and tool security, git connections per organization, Jira OAuth per user."""

import time
from unittest.mock import patch

import pytest

from app.core import storage
from app.core.storage_cache import clear_storage_caches
from app.integrations.executor import IntegrationToolExecutor, SafeMCPHttpClient, validate_mcp_endpoint_url
from app.integrations.jira.integration import JiraIntegration
from tests.fake_session import GLOBAL_FAKE_STORAGE


@pytest.fixture(autouse=True)
def clean_storage():
  clear_storage_caches()
  GLOBAL_FAKE_STORAGE.clear()
  yield
  clear_storage_caches()
  GLOBAL_FAKE_STORAGE.clear()


@pytest.mark.asyncio
async def test_mcp_rejects_internal_endpoints_and_unauthorized_tools():
  for url in [
    "http://localhost:8000/sse",
    "http://10.0.0.1/mcp",
    "http://172.16.0.5/mcp",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/sse",
    "ftp://example.com/server",
    "http://external.com:22/sse",
  ]:
    assert validate_mcp_endpoint_url(url, resolve_dns=False) is False, url
  assert validate_mcp_endpoint_url("https://mcp.external-service.com/sse", resolve_dns=False) is True

  with pytest.raises(ValueError, match="rejected by SSRF security policy"):
    await SafeMCPHttpClient().post("http://127.0.0.1:8080/eval", json_data={})

  executor = IntegrationToolExecutor(organization_id="org-test")
  res = await executor.execute_tool(
    provider="jira", tool_name="dangerous_operation", arguments={}, allowed_tools=["get_issues"],
  )
  assert res["ok"] is False and "not authorized" in res["error"]
  assert executor.can_invoke_tool("jira", "get_issues", ["*"]) is False
  assert executor.can_invoke_tool("jira", "get_issues", []) is False
  assert executor.can_invoke_tool("jira", "get_issues", None) is False
  assert executor.can_invoke_tool("jira", "get_issues", ["get_issues"]) is True


def test_git_connections_are_isolated_per_organization():
  storage.save_connection("github", {"access_token": "ghp_org1", "selected_repos": ["acme/backend"]}, org_id="org-1")
  storage.save_connection("gitlab", {"access_token": "glpat-org1"}, org_id="org-1")
  storage.save_connection("gitlab", {"access_token": "glpat-org2"}, org_id="org-2")

  github = storage.load_connection("github", org_id="org-1")
  assert github["access_token"] == "ghp_org1" and github["selected_repos"] == ["acme/backend"]
  assert storage.load_connection("gitlab", org_id="org-1")["access_token"] == "glpat-org1"
  assert storage.load_connection("gitlab", org_id="org-2")["access_token"] == "glpat-org2"


@pytest.mark.asyncio
async def test_jira_personal_connection_and_oauth_state():
  storage.save_user_integration("usr-a", "jira", {"access_token": "token-a"})
  storage.save_user_integration("usr-b", "jira", {"access_token": "token-b"})
  assert storage.load_user_integration("usr-a", "jira")["access_token"] == "token-a"
  assert storage.load_user_integration("usr-b", "jira")["access_token"] == "token-b"
  # No silent fallback to an organization connection for a user without a personal one.
  storage.save_connection("jira", {"site_url": "https://org.atlassian.net"})
  assert storage.load_user_integration("usr-unknown", "jira") is None

  jira = JiraIntegration()
  user_id = "usr-oauth"
  with patch("app.integrations.jira.integration.get_jira_oauth_config") as cfg:
    cfg.return_value = {
      "configured": True, "client_id": "id", "client_secret": "sec",
      "redirect_uri": "http://127.0.0.1:6728/api/integrations/jira/callback",
    }
    started = await jira.start_oauth(user_id=user_id)
    assert user_id in started.state

    with pytest.raises(ValueError, match="Invalid OAuth state"):
      await jira.handle_oauth_callback(code="c", state="forged-state")

    expired = f"{user_id}::{int(time.time()) - 1000}::old"
    storage.save_user_integration(user_id, "jira", {"oauth_state": expired})
    with pytest.raises(ValueError, match="expired"):
      await jira.handle_oauth_callback(code="c", state=expired)
