"""GitHub integration — OAuth with repo selection."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.integration_config import get_github_oauth_config
from app.core.storage import delete_connection, load_connection, save_connection
from app.integrations.base import (
  AuthMethod,
  AuthStartResponse,
  Capability,
  ConnectionStatus,
  Integration,
  IntegrationInfo,
  TestConnectionResult,
)

API = "https://api.github.com"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_SCOPES = "repo read:user"
HEADERS_BASE = {
  "Accept": "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
}


class GitHubIntegration(Integration):
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
    oauth_configured = get_github_oauth_config()["configured"]
    if not self._is_connected(data):
      return IntegrationInfo(
        id=self.id,
        name=self.name,
        description=self.description,
        status=ConnectionStatus.NOT_CONNECTED,
        auth_methods=[AuthMethod.OAUTH],
        capabilities=self.get_capabilities(),
        oauth_configured=oauth_configured,
      )

    assert data is not None
    return IntegrationInfo(
      id=self.id,
      name=self.name,
      description=self.description,
      status=ConnectionStatus.CONNECTED,
      auth_methods=[AuthMethod.OAUTH],
      capabilities=self.get_capabilities(),
      account_label=data.get("account_login"),
      workspace_label="GitHub",
      details={
        "auth_method": data.get("auth_method"),
        "selected_repos": data.get("selected_repos", []),
      },
      oauth_configured=oauth_configured,
    )

  def _is_connected(self, data: dict[str, Any] | None) -> bool:
    if not data:
      return False
    return data.get("auth_method") == AuthMethod.OAUTH.value and bool(data.get("access_token"))

  async def start_oauth(self) -> AuthStartResponse:
    oauth = get_github_oauth_config()
    if not oauth["configured"]:
      raise ValueError(
        "GitHub OAuth is not configured. Add Client ID and Secret in Integrations → GitHub OAuth setup, "
        "or set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env"
      )

    state = secrets.token_urlsafe(24)
    pending = load_connection(self.id) or {}
    pending["oauth_state"] = state
    save_connection(self.id, pending)

    params = urlencode(
      {
        "client_id": oauth["client_id"],
        "redirect_uri": oauth["redirect_uri"],
        "scope": GITHUB_SCOPES,
        "state": state,
      }
    )
    return AuthStartResponse(
      authorization_url=f"{GITHUB_AUTHORIZE_URL}?{params}",
      state=state,
      auth_method=AuthMethod.OAUTH,
    )

  async def handle_oauth_callback(self, code: str, state: str) -> IntegrationInfo:
    oauth = get_github_oauth_config()
    pending = load_connection(self.id) or {}
    expected = pending.get("oauth_state")
    if not expected or expected != state:
      raise ValueError("Invalid OAuth state. Restart the GitHub connection flow.")

    async with httpx.AsyncClient(timeout=30.0) as client:
      token_response = await client.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        json={
          "client_id": oauth["client_id"],
          "client_secret": oauth["client_secret"],
          "code": code,
          "redirect_uri": oauth["redirect_uri"],
        },
      )
      if token_response.status_code >= 400:
        raise ValueError(f"GitHub token exchange failed ({token_response.status_code}): {token_response.text}")
      tokens = token_response.json()
      access_token = tokens.get("access_token")
      if not access_token:
        raise ValueError("GitHub token exchange did not return an access token.")

      user_response = await client.get(
        f"{API}/user",
        headers={**HEADERS_BASE, "Authorization": f"Bearer {access_token}"},
      )
      user_response.raise_for_status()
      user = user_response.json()

    existing = load_connection(self.id) or {}
    selected_repos = existing.get("selected_repos") or []
    payload = {
      "auth_method": AuthMethod.OAUTH.value,
      "access_token": access_token,
      "token_type": tokens.get("token_type", "bearer"),
      "scope": tokens.get("scope"),
      "account_login": user.get("login"),
      "account_label": user.get("login"),
      "account_name": user.get("name"),
      "selected_repos": selected_repos,
    }
    save_connection(self.id, payload)
    return self.get_info()

  async def disconnect(self) -> None:
    delete_connection(self.id)

  async def authenticate(self) -> bool:
    data = load_connection(self.id)
    return self._is_connected(data)

  async def test_connection(self) -> TestConnectionResult:
    data = load_connection(self.id)
    if not data or not self._is_connected(data):
      return TestConnectionResult(ok=False, message="GitHub is not connected.")

    try:
      async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API}/user", headers=self._headers())
        response.raise_for_status()
        user = response.json()
      return TestConnectionResult(
        ok=True,
        message="GitHub connection is healthy.",
        details={
          "login": user.get("login"),
          "selected_repos": data.get("selected_repos", []),
          "auth_method": data.get("auth_method"),
        },
      )
    except Exception as exc:
      return TestConnectionResult(ok=False, message=str(exc))

  def _token(self) -> str:
    data = load_connection(self.id)
    if not data:
      raise ValueError("GitHub is not connected.")
    if data.get("auth_method") == AuthMethod.OAUTH.value and data.get("access_token"):
      return str(data["access_token"])
    raise ValueError("GitHub is not connected.")

  def _headers(self) -> dict[str, str]:
    return {**HEADERS_BASE, "Authorization": f"Bearer {self._token()}"}

  def selected_repos(self) -> list[str]:
    data = load_connection(self.id) or {}
    return list(data.get("selected_repos") or [])

  async def update_selected_repos(self, repos: list[str]) -> IntegrationInfo:
    data = load_connection(self.id)
    if not data or not self._is_connected(data):
      raise ValueError("GitHub is not connected.")
    data["selected_repos"] = repos
    save_connection(self.id, data)
    return self.get_info()

  async def get_repositories(self, *, max_results: int = 100) -> list[dict[str, Any]]:
    if not await self.authenticate():
      raise ValueError("GitHub is not connected.")

    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.get(
        f"{API}/user/repos",
        headers=self._headers(),
        params={
          "per_page": min(max_results, 100),
          "sort": "updated",
          "affiliation": "owner,collaborator,organization_member",
        },
      )
      response.raise_for_status()
      repos = response.json()

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

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        response = await client.get(
          f"{API}/repos/{repo}/pulls",
          headers=self._headers(),
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

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        response = await client.get(
          f"{API}/repos/{repo}/commits",
          headers=self._headers(),
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
        headers=self._headers(),
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
