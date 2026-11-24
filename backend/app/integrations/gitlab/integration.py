"""GitLab integration — OAuth with project selection."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.core.integration_config import get_gitlab_oauth_config
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

DEFAULT_HOST = "https://gitlab.com"


class GitLabIntegration(Integration):
  id = "gitlab"
  name = "GitLab"
  description = "Connect GitLab projects for merge requests, commits, and issues."

  def get_capabilities(self) -> list[Capability]:
    return [
      Capability.GET_PULL_REQUESTS,
      Capability.GET_COMMITS,
      Capability.GET_FILES_CHANGED,
      Capability.GET_ISSUES,
      Capability.GET_REPOSITORIES,
    ]

  def _api_base(self, data: dict[str, Any] | None = None) -> str:
    payload = data or load_connection(self.id) or {}
    stored = str(payload.get("api_base") or "").strip()
    if stored:
      return stored.rstrip("/")
    base_url = str(payload.get("base_url") or DEFAULT_HOST).strip().rstrip("/")
    return f"{base_url}/api/v4"

  def get_info(self) -> IntegrationInfo:
    data = load_connection(self.id)
    oauth_configured = get_gitlab_oauth_config()["configured"]
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
    host = str(data.get("base_url") or DEFAULT_HOST).replace("https://", "").replace("http://", "")
    return IntegrationInfo(
      id=self.id,
      name=self.name,
      description=self.description,
      status=ConnectionStatus.CONNECTED,
      auth_methods=[AuthMethod.OAUTH],
      capabilities=self.get_capabilities(),
      account_label=data.get("account_login"),
      workspace_label=host,
      details={
        "auth_method": data.get("auth_method"),
        "selected_repos": data.get("selected_repos", []),
        "base_url": data.get("base_url") or DEFAULT_HOST,
      },
      oauth_configured=oauth_configured,
    )

  def _is_connected(self, data: dict[str, Any] | None) -> bool:
    if not data:
      return False
    return data.get("auth_method") == AuthMethod.OAUTH.value and bool(data.get("access_token"))

  async def start_oauth(self) -> AuthStartResponse:
    oauth = get_gitlab_oauth_config()
    if not oauth["configured"]:
      raise ValueError(
        "GitLab OAuth is not configured. Add Application ID and Secret in Integrations → GitLab OAuth setup."
      )

    state = secrets.token_urlsafe(24)
    pending = load_connection(self.id) or {}
    pending["oauth_state"] = state
    save_connection(self.id, pending)

    base_url = oauth.get("base_url") or DEFAULT_HOST
    params = urlencode(
      {
        "client_id": oauth["client_id"],
        "redirect_uri": oauth["redirect_uri"],
        "response_type": "code",
        "scope": "read_api read_user",
        "state": state,
      }
    )
    return AuthStartResponse(
      authorization_url=f"{base_url.rstrip('/')}/oauth/authorize?{params}",
      state=state,
      auth_method=AuthMethod.OAUTH,
    )

  async def handle_oauth_callback(self, code: str, state: str) -> IntegrationInfo:
    oauth = get_gitlab_oauth_config()
    pending = load_connection(self.id) or {}
    expected = pending.get("oauth_state")
    if not expected or expected != state:
      raise ValueError("Invalid OAuth state. Restart the GitLab connection flow.")

    base_url = oauth.get("base_url") or DEFAULT_HOST
    api_base = f"{base_url.rstrip('/')}/api/v4"

    async with httpx.AsyncClient(timeout=30.0) as client:
      token_response = await client.post(
        f"{base_url.rstrip('/')}/oauth/token",
        data={
          "client_id": oauth["client_id"],
          "client_secret": oauth["client_secret"],
          "code": code,
          "grant_type": "authorization_code",
          "redirect_uri": oauth["redirect_uri"],
        },
      )
      if token_response.status_code >= 400:
        raise ValueError(f"GitLab token exchange failed ({token_response.status_code}): {token_response.text}")
      tokens = token_response.json()
      access_token = tokens.get("access_token")
      if not access_token:
        raise ValueError("GitLab token exchange did not return an access token.")

      user_response = await client.get(
        f"{api_base}/user",
        headers={"Authorization": f"Bearer {access_token}"},
      )
      user_response.raise_for_status()
      user = user_response.json()

    existing = load_connection(self.id) or {}
    payload = {
      "auth_method": AuthMethod.OAUTH.value,
      "access_token": access_token,
      "refresh_token": tokens.get("refresh_token"),
      "token_type": tokens.get("token_type", "Bearer"),
      "base_url": base_url.rstrip("/"),
      "api_base": api_base,
      "account_login": user.get("username"),
      "account_label": user.get("username"),
      "account_name": user.get("name"),
      "selected_repos": existing.get("selected_repos") or [],
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
    if not data:
      return TestConnectionResult(ok=False, message="GitLab is not connected.")

    try:
      async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
          f"{self._api_base(data)}/user",
          headers=self._headers(),
        )
        response.raise_for_status()
        user = response.json()
      return TestConnectionResult(
        ok=True,
        message="GitLab connection is healthy.",
        details={
          "username": user.get("username"),
          "selected_repos": data.get("selected_repos", []),
          "base_url": data.get("base_url") or DEFAULT_HOST,
        },
      )
    except Exception as exc:
      return TestConnectionResult(ok=False, message=str(exc))

  def _headers(self) -> dict[str, str]:
    data = load_connection(self.id)
    if not data:
      raise ValueError("GitLab is not connected.")
    if data.get("auth_method") == AuthMethod.OAUTH.value and data.get("access_token"):
      return {"Authorization": f"Bearer {data['access_token']}"}
    raise ValueError("GitLab is not connected.")

  def selected_repos(self) -> list[str]:
    data = load_connection(self.id) or {}
    return list(data.get("selected_repos") or [])

  async def update_selected_repos(self, repos: list[str]) -> IntegrationInfo:
    data = load_connection(self.id)
    if not data or not self._is_connected(data):
      raise ValueError("GitLab is not connected.")
    data["selected_repos"] = repos
    save_connection(self.id, data)
    return self.get_info()

  def _encode_project(self, path: str) -> str:
    return quote(path, safe="")

  async def get_repositories(self, *, max_results: int = 100) -> list[dict[str, Any]]:
    if not await self.authenticate():
      raise ValueError("GitLab is not connected.")

    data = load_connection(self.id) or {}
    api_base = self._api_base(data)

    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.get(
        f"{api_base}/projects",
        headers=self._headers(),
        params={
          "membership": "true",
          "order_by": "last_activity_at",
          "per_page": min(max_results, 100),
        },
      )
      response.raise_for_status()
      projects = response.json()

    selected = set(self.selected_repos())
    return [
      {
        "full_name": project.get("path_with_namespace"),
        "name": project.get("name"),
        "private": project.get("visibility") != "public",
        "html_url": project.get("web_url"),
        "updated_at": project.get("last_activity_at"),
        "default_branch": project.get("default_branch"),
        "selected": project.get("path_with_namespace") in selected,
      }
      for project in projects
    ]

  async def get_pull_requests(
    self,
    *,
    state: str = "all",
    max_results: int = 30,
  ) -> list[dict[str, Any]]:
    return await self.get_merge_requests(state=state, max_results=max_results)

  async def get_merge_requests(
    self,
    *,
    state: str = "all",
    max_results: int = 30,
  ) -> list[dict[str, Any]]:
    repos = self.selected_repos()
    if not repos:
      raise ValueError("No GitLab projects selected. Choose projects in Integrations.")

    data = load_connection(self.id) or {}
    api_base = self._api_base(data)
    gitlab_state = "opened" if state == "open" else state

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        params: dict[str, str | int] = {
          "per_page": min(max_results, 30),
          "order_by": "updated_at",
        }
        if gitlab_state != "all":
          params["state"] = gitlab_state

        response = await client.get(
          f"{api_base}/projects/{self._encode_project(repo)}/merge_requests",
          headers=self._headers(),
          params=params,
        )
        response.raise_for_status()
        for mr in response.json():
          results.append(
            {
              "repo": repo,
              "number": mr.get("iid"),
              "title": mr.get("title"),
              "state": mr.get("state"),
              "user": (mr.get("author") or {}).get("username"),
              "merged_at": mr.get("merged_at"),
              "updated_at": mr.get("updated_at"),
              "html_url": mr.get("web_url"),
              "draft": mr.get("draft") or mr.get("work_in_progress"),
            }
          )
    results.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return results[:max_results]

  async def get_commits(self, *, max_results: int = 30) -> list[dict[str, Any]]:
    repos = self.selected_repos()
    if not repos:
      raise ValueError("No GitLab projects selected. Choose projects in Integrations.")

    data = load_connection(self.id) or {}
    api_base = self._api_base(data)
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        response = await client.get(
          f"{api_base}/projects/{self._encode_project(repo)}/repository/commits",
          headers=self._headers(),
          params={"per_page": min(max_results, 30)},
        )
        response.raise_for_status()
        for commit in response.json():
          results.append(
            {
              "repo": repo,
              "sha": (commit.get("id") or "")[:7],
              "message": (commit.get("title") or commit.get("message") or "").split("\n")[0],
              "author": (commit.get("author_name") or (commit.get("author") or {}).get("name")),
              "date": commit.get("committed_date") or commit.get("created_at"),
              "html_url": commit.get("web_url"),
            }
          )
    results.sort(key=lambda item: item.get("date") or "", reverse=True)
    return results[:max_results]

  async def get_issues(self, *, max_results: int = 30) -> list[dict[str, Any]]:
    repos = self.selected_repos()
    if not repos:
      raise ValueError("No GitLab projects selected. Choose projects in Integrations.")

    data = load_connection(self.id) or {}
    api_base = self._api_base(data)
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
      for repo in repos:
        response = await client.get(
          f"{api_base}/projects/{self._encode_project(repo)}/issues",
          headers=self._headers(),
          params={"per_page": min(max_results, 30), "order_by": "updated_at"},
        )
        response.raise_for_status()
        for issue in response.json():
          results.append(
            {
              "repo": repo,
              "number": issue.get("iid"),
              "title": issue.get("title"),
              "state": issue.get("state"),
              "user": (issue.get("author") or {}).get("username"),
              "updated_at": issue.get("updated_at"),
              "html_url": issue.get("web_url"),
            }
          )
    results.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return results[:max_results]

  async def get_files_changed(self, *, pr_number: int, repo: str | None = None) -> list[dict[str, Any]]:
    selected = self.selected_repos()
    target_repo = repo or (selected[0] if selected else None)
    if not target_repo:
      raise ValueError("Provide a project or select projects first.")
    if target_repo not in selected:
      raise ValueError("The project is not enabled by the administrator.")

    data = load_connection(self.id) or {}
    api_base = self._api_base(data)

    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.get(
        f"{api_base}/projects/{self._encode_project(target_repo)}/merge_requests/{pr_number}/changes",
        headers=self._headers(),
      )
      response.raise_for_status()
      body = response.json()

    return [
      {
        "repo": target_repo,
        "filename": item.get("new_path") or item.get("old_path"),
        "status": "renamed" if item.get("renamed_file") else "modified",
        "additions": None,
        "deletions": None,
        "changes": None,
      }
      for item in body.get("changes") or []
    ]
