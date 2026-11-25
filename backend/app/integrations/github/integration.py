"""GitHub integration: a read-only GitHub App installation, with repository selection.

The organization connects one GitHub App, installed only on the repositories it needs and holding
read-only permissions. The application signs a short-lived JWT with the App's private key and exchanges
it for an installation token that lasts one hour; that token is renewed automatically and never stored.
There is no personal token and no OAuth flow: the credential belongs to the App, not to a person.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
import jwt

from app.core.storage import delete_connection, load_connection, save_connection
from app.integrations.base import (
  AuthMethod,
  Capability,
  ConnectionStatus,
  IntegrationInfo,
  TestConnectionResult,
)
from app.integrations.git_hosting import GitHostingIntegration
from app.integrations.service_accounts import (
  GITHUB_ALLOWED_PERMISSIONS,
  GITHUB_REQUIRED_PERMISSIONS,
  check_app_permissions,
)

API = "https://api.github.com"
HEADERS_BASE = {
  "Accept": "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
}
# Renew an installation token this many seconds before GitHub says it expires.
TOKEN_REFRESH_MARGIN = 300

# installation id -> (token, unix expiry). In memory only: a restart simply mints a new one.
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def clear_token_cache() -> None:
  _TOKEN_CACHE.clear()


def _normalize_private_key(value: str) -> str:
  key = (value or "").strip().replace("\\n", "\n")
  if "BEGIN" not in key or "PRIVATE KEY" not in key:
    raise ValueError("The private key must be the PEM file generated for the GitHub App.")
  return key


def _validate_app_id(app_id: str) -> str:
  value = (app_id or "").strip()
  if not value or not value.replace("-", "").replace("_", "").isalnum():
    raise ValueError("A valid GitHub App ID is required.")
  return value


def _select_installation(installations: list[dict[str, Any]], wanted: str | None) -> dict[str, Any]:
  """The installation to use: the requested one, or the only active one. Suspended installations never count."""
  active = [i for i in installations if not i.get("suspended_at")]
  if wanted:
    match = next((i for i in active if str(i.get("id")) == wanted.strip()), None)
    if match is None:
      raise ValueError("That installation does not exist for this GitHub App, or it is suspended.")
    return match
  if not active:
    raise ValueError("The GitHub App is not installed anywhere. Install it on the repositories to expose.")
  if len(active) > 1:
    raise ValueError("The GitHub App has several installations: provide the installation ID to use.")
  return active[0]


def _connection_record(
  app_id: str,
  key: str,
  app_info: dict[str, Any],
  installation: dict[str, Any],
  token_body: dict[str, Any],
  *,
  selected_repos: list[str],
  configured_by: str | None,
) -> dict[str, Any]:
  """What is stored for a validated installation. Raises ValueError unless its permissions are read-only."""
  permissions = check_app_permissions(token_body.get("permissions") or installation.get("permissions") or {})
  login = (installation.get("account") or {}).get("login")
  return {
    "auth_method": AuthMethod.SERVICE_ACCOUNT.value,
    "app_id": app_id,
    "app_name": app_info.get("name") or app_info.get("slug"),
    "private_key": key,
    "installation_id": str(installation["id"]),
    "account_login": login,
    "account_label": login,
    "permissions": permissions,
    "repository_selection": token_body.get("repository_selection") or installation.get("repository_selection"),
    "configured_by": configured_by,
    "configured_at": datetime.now(timezone.utc).isoformat(),
    "selected_repos": selected_repos,
  }


def _app_jwt(app_id: str, private_key: str) -> str:
  now = int(time.time())
  try:
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, private_key, algorithm="RS256")
  except Exception as exc:
    raise ValueError("The private key could not be used to sign requests. Check that it is the App's RSA key.") from exc


def _expiry_epoch(value: Any) -> float:
  try:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
  except ValueError:
    return time.time() + 3000


class GitHubIntegration(GitHostingIntegration):
  id = "github"
  name = "GitHub"
  description = "Connect GitHub repositories for PRs, commits, and changed files."

  def get_capabilities(self) -> list[Capability]:
    return [
      Capability.GET_PULL_REQUESTS,
      Capability.GET_COMMITS,
      Capability.GET_FILES_CHANGED,
      Capability.GET_REPOSITORIES,
    ]

  def get_info(self) -> IntegrationInfo:
    data = load_connection(self.id)
    if not self._is_connected(data):
      return IntegrationInfo(
        id=self.id,
        name=self.name,
        description=self.description,
        status=ConnectionStatus.NOT_CONNECTED,
        auth_methods=[AuthMethod.SERVICE_ACCOUNT],
        capabilities=self.get_capabilities(),
      )

    assert data is not None
    return IntegrationInfo(
      id=self.id,
      name=self.name,
      description=self.description,
      status=ConnectionStatus.CONNECTED,
      auth_methods=[AuthMethod.SERVICE_ACCOUNT],
      capabilities=self.get_capabilities(),
      account_label=data.get("account_login"),
      workspace_label="GitHub",
      details={
        "auth_method": data.get("auth_method"),
        "selected_repos": data.get("selected_repos", []),
        "app_id": data.get("app_id"),
        "app_name": data.get("app_name"),
        "installation_id": data.get("installation_id"),
        "permissions": data.get("permissions") or {},
        "repository_selection": data.get("repository_selection"),
        "configured_by": data.get("configured_by"),
        "configured_at": data.get("configured_at"),
      },
    )

  def _is_connected(self, data: dict[str, Any] | None) -> bool:
    if not data:
      return False
    return (
      data.get("auth_method") == AuthMethod.SERVICE_ACCOUNT.value
      and bool(data.get("app_id"))
      and bool(data.get("private_key"))
      and bool(data.get("installation_id"))
    )

  # -- GitHub App credential ------------------------------------------------------------------

  @staticmethod
  async def _mint_installation_token(
    client: httpx.AsyncClient, app_id: str, private_key: str, installation_id: str
  ) -> dict[str, Any]:
    """Exchange the App JWT for an installation token. Returns GitHub's token response."""
    response = await client.post(
      f"{API}/app/installations/{installation_id}/access_tokens",
      headers={**HEADERS_BASE, "Authorization": f"Bearer {_app_jwt(app_id, private_key)}"},
    )
    if response.status_code in (401, 403):
      raise ValueError("GitHub rejected the App credentials: check the App ID and the private key.")
    if response.status_code == 404:
      raise ValueError("The GitHub App installation was not found. It may have been uninstalled.")
    response.raise_for_status()
    body = response.json()
    if not body.get("token"):
      raise ValueError("GitHub did not return an installation token.")
    return body

  async def connect_with_github_app(
    self,
    app_id: str,
    private_key: str,
    *,
    installation_id: str | None = None,
    selected_repos: list[str] | None = None,
    configured_by: str | None = None,
  ) -> IntegrationInfo:
    """Connect the organization through a GitHub App installation.

    Everything is checked before anything is stored: the key must sign, the installation must exist and be
    active, and its permissions must be read-only and no more than the integration needs.
    """
    app_id = _validate_app_id(app_id)
    key = _normalize_private_key(private_key)
    app_info, installation, token_body = await self._discover_installation(app_id, key, installation_id)
    existing = load_connection(self.id) or {}
    save_connection(
      self.id,
      _connection_record(
        app_id, key, app_info, installation, token_body,
        selected_repos=selected_repos if selected_repos is not None else existing.get("selected_repos") or [],
        configured_by=configured_by,
      ),
    )
    clear_token_cache()
    return self.get_info()

  async def _discover_installation(
    self, app_id: str, key: str, wanted_installation: str | None
  ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """What GitHub says about the App, the installation to use and a first installation token."""
    headers = {**HEADERS_BASE, "Authorization": f"Bearer {_app_jwt(app_id, key)}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
      app_response = await client.get(f"{API}/app", headers=headers)
      if app_response.status_code in (401, 403):
        raise ValueError("GitHub rejected the App credentials: check the App ID and the private key.")
      app_response.raise_for_status()

      installs_response = await client.get(f"{API}/app/installations", headers=headers, params={"per_page": 100})
      installs_response.raise_for_status()
      installation = _select_installation(installs_response.json(), wanted_installation)

      token_body = await self._mint_installation_token(client, app_id, key, str(installation["id"]))
    return app_response.json(), installation, token_body

  async def _installation_token(self, *, force_refresh: bool = False) -> str:
    data = load_connection(self.id)
    if not self._is_connected(data):
      raise ValueError("GitHub is not connected.")
    assert data is not None
    installation_id = str(data["installation_id"])
    cached = _TOKEN_CACHE.get(installation_id)
    if cached and not force_refresh and cached[1] - TOKEN_REFRESH_MARGIN > time.time():
      return cached[0]
    async with httpx.AsyncClient(timeout=30.0) as client:
      body = await self._mint_installation_token(client, str(data["app_id"]), str(data["private_key"]), installation_id)
    # A token whose permissions grew after connecting is not accepted.
    check_app_permissions(body.get("permissions") or {})
    _TOKEN_CACHE[installation_id] = (str(body["token"]), _expiry_epoch(body.get("expires_at")))
    return str(body["token"])

  async def _headers(self) -> dict[str, str]:
    return {**HEADERS_BASE, "Authorization": f"Bearer {await self._installation_token()}"}

  # -- contract ---------------------------------------------------------------------------------

  async def disconnect(self) -> None:
    delete_connection(self.id)
    clear_token_cache()

  async def authenticate(self) -> bool:
    data = load_connection(self.id)
    return self._is_connected(data)

  async def test_connection(self) -> TestConnectionResult:
    data = load_connection(self.id)
    if not data or not self._is_connected(data):
      return TestConnectionResult(ok=False, message="GitHub is not connected.")

    try:
      # Always mint a fresh token so permissions are re-checked on every test.
      token = await self._installation_token(force_refresh=True)
      async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
          f"{API}/installation/repositories",
          headers={**HEADERS_BASE, "Authorization": f"Bearer {token}"},
          params={"per_page": 1},
        )
        response.raise_for_status()
        total = response.json().get("total_count")
      return TestConnectionResult(
        ok=True,
        message="GitHub connection is healthy.",
        details={
          "account": data.get("account_login"),
          "installation_id": data.get("installation_id"),
          "permissions": data.get("permissions") or {},
          "accessible_repositories": total,
          "selected_repos": data.get("selected_repos", []),
          "auth_method": data.get("auth_method"),
          "allowed_permissions": sorted(GITHUB_ALLOWED_PERMISSIONS),
          "required_permissions": sorted(GITHUB_REQUIRED_PERMISSIONS),
        },
      )
    except Exception as exc:
      return TestConnectionResult(ok=False, message=str(exc))

  async def get_repositories(self, *, max_results: int = 100) -> list[dict[str, Any]]:
    if not await self.authenticate():
      raise ValueError("GitHub is not connected.")

    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.get(
        f"{API}/installation/repositories",
        headers=await self._headers(),
        params={"per_page": min(max_results, 100)},
      )
      response.raise_for_status()
      repos = response.json().get("repositories") or []

    selected = set(self.selected_repos())
    return [
      {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "private": repo.get("private"),
        "html_url": repo.get("html_url"),
        "updated_at": repo.get("updated_at"),
        "default_branch": repo.get("default_branch"),
        "selected": repo.get("full_name") in selected,
      }
      for repo in repos
    ]

  async def get_pull_requests(
    self,
    *,
    state: str = "all",
    max_results: int = 30,
  ) -> list[dict[str, Any]]:
    repos = self.selected_repos()
    if not repos:
      raise ValueError("No GitHub repositories selected. Choose repos in Integrations.")

    headers = await self._headers()
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        response = await client.get(
          f"{API}/repos/{repo}/pulls",
          headers=headers,
          params={"state": state, "per_page": min(max_results, 30), "sort": "updated"},
        )
        response.raise_for_status()
        for pr in response.json():
          results.append(
            {
              "repo": repo,
              "number": pr.get("number"),
              "title": pr.get("title"),
              "state": pr.get("state"),
              "user": (pr.get("user") or {}).get("login"),
              "merged_at": pr.get("merged_at"),
              "updated_at": pr.get("updated_at"),
              "html_url": pr.get("html_url"),
              "draft": pr.get("draft"),
            }
          )
    results.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return results[:max_results]

  async def get_commits(self, *, max_results: int = 30) -> list[dict[str, Any]]:
    repos = self.selected_repos()
    if not repos:
      raise ValueError("No GitHub repositories selected. Choose repos in Integrations.")

    headers = await self._headers()
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        response = await client.get(
          f"{API}/repos/{repo}/commits",
          headers=headers,
          params={"per_page": min(max_results, 30)},
        )
        response.raise_for_status()
        for commit in response.json():
          commit_data = commit.get("commit") or {}
          author = commit_data.get("author") or {}
          results.append(
            {
              "repo": repo,
              "sha": (commit.get("sha") or "")[:7],
              "message": (commit_data.get("message") or "").split("\n")[0],
              "author": author.get("name"),
              "date": author.get("date"),
              "html_url": commit.get("html_url"),
            }
          )
    results.sort(key=lambda item: item.get("date") or "", reverse=True)
    return results[:max_results]

  async def get_files_changed(self, *, pr_number: int, repo: str | None = None) -> list[dict[str, Any]]:
    selected = self.selected_repos()
    target_repo = repo or (selected[0] if selected else None)
    if not target_repo:
      raise ValueError("Provide a repo or select repositories first.")
    if target_repo not in selected:
      raise ValueError("The repository is not enabled by the administrator.")

    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.get(
        f"{API}/repos/{target_repo}/pulls/{pr_number}/files",
        headers=await self._headers(),
        params={"per_page": 100},
      )
      response.raise_for_status()
      files = response.json()

    return [
      {
        "repo": target_repo,
        "filename": item.get("filename"),
        "status": item.get("status"),
        "additions": item.get("additions"),
        "deletions": item.get("deletions"),
        "changes": item.get("changes"),
      }
      for item in files
    ]
