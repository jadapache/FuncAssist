from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.ai.logging import log_security_event
from app.api.deps import get_current_user
from app.core.settings import get_settings
from app.integrations.base import AuthMethod, IntegrationInfo, TestConnectionResult
from app.integrations.registry import GIT_HOSTING_IDS, registry
from app.integrations.sync import load_sync_cache, sync_integration

router = APIRouter(
  prefix="/integrations",
  tags=["integrations"],
)


# Jira connections belong to each user. Every other integration is shared by the whole organization,
# so only an administrator may connect, disconnect or change what it exposes.
PERSONAL_INTEGRATIONS = frozenset({"jira"})


def _require_admin_for_organization(integration_id: str, current_user: dict) -> None:
  if integration_id not in PERSONAL_INTEGRATIONS and current_user.get("role") != "admin":
    raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")


def _require_git_hosting(integration_id: str):
  if integration_id not in GIT_HOSTING_IDS:
    raise HTTPException(
      status_code=501,
      detail="Repositories endpoint is only available for GitHub and GitLab.",
    )
  return registry.get(integration_id)


class SelectedReposRequest(BaseModel):
  selected_repos: list[str]


class SelectedProjectsRequest(BaseModel):
  selected_projects: list[str]


@router.get("", response_model=list[IntegrationInfo])
async def list_integrations() -> list[IntegrationInfo]:
  return registry.list_info()


@router.get("/auth-methods")
async def auth_methods() -> dict[str, list[str]]:
  return {
    "methods": [AuthMethod.OAUTH.value],
  }


@router.get("/jira/callback")
async def jira_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
  settings = get_settings()
  frontend = settings.frontend_url.rstrip("/")

  if error:
    return RedirectResponse(f"{frontend}/integrations?jira=error&message={quote(error)}")
  if not code or not state:
    return RedirectResponse(f"{frontend}/integrations?jira=error&message=missing_code")

  try:
    jira = registry.get("jira")
    await jira.handle_oauth_callback(code, state)
    await sync_integration("jira", user_id=jira.user_id_from_state(state))  # type: ignore[attr-defined]
  except Exception as exc:
    return RedirectResponse(f"{frontend}/integrations?jira=error&message={quote(str(exc))}")

  return RedirectResponse(f"{frontend}/integrations?jira=connected")


@router.get("/{integration_id}", response_model=IntegrationInfo)
async def get_integration(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  try:
    integration = registry.get(integration_id)
    user_id = current_user["id"]
    if integration_id == "jira" and hasattr(integration, "get_info"):
      return integration.get_info(user_id=user_id)
    return integration.get_info()
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/oauth/start")
async def start_oauth(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> dict:
  _require_admin_for_organization(integration_id, current_user)
  if integration_id != "jira":
    raise HTTPException(status_code=501, detail="OAuth is only used by Jira. GitHub and GitLab use service accounts.")
  try:
    integration = registry.get(integration_id)
    result = await integration.start_oauth(user_id=current_user["id"])
    return result.model_dump()
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except NotImplementedError as exc:
    raise HTTPException(status_code=501, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


class ServiceAccountRequest(BaseModel):
  token: str = Field(min_length=1, max_length=512)
  base_url: str | None = Field(default=None, max_length=300)
  selected_repos: list[str] | None = None


class GitHubAppRequest(BaseModel):
  app_id: str = Field(min_length=1, max_length=64)
  private_key: str = Field(min_length=1, max_length=8192)
  installation_id: str | None = Field(default=None, max_length=64)
  selected_repos: list[str] | None = None


async def _finish_service_account(integration_id: str, info: IntegrationInfo, current_user: dict) -> IntegrationInfo:
  log_security_event(
    "service_account_connected",
    admin=str(current_user["id"]), provider=integration_id,
    scopes=info.details.get("scopes"), permissions=info.details.get("permissions"),
    expires_at=info.details.get("expires_at"),
  )
  try:
    await sync_integration(integration_id)
  except Exception:
    pass
  return info


@router.post("/github/service-account", response_model=IntegrationInfo)
async def connect_github_app(
  body: GitHubAppRequest,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  """Connect GitHub through a read-only GitHub App installation (administrators only)."""
  _require_admin_for_organization("github", current_user)
  try:
    info = await registry.get("github").connect_with_github_app(  # type: ignore[attr-defined]
      body.app_id,
      body.private_key,
      installation_id=body.installation_id,
      selected_repos=body.selected_repos,
      configured_by=str(current_user["id"]),
    )
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail="Could not reach GitHub to validate the App.") from exc
  return await _finish_service_account("github", info, current_user)


@router.post("/{integration_id}/service-account", response_model=IntegrationInfo)
async def connect_service_account(
  integration_id: str,
  body: ServiceAccountRequest,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  """Connect GitLab with a dedicated read-only bot credential (administrators only)."""
  _require_admin_for_organization(integration_id, current_user)
  try:
    integration = registry.get(integration_id)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  if integration_id != "gitlab":
    raise HTTPException(status_code=501, detail="Token service accounts are only available for GitLab.")

  try:
    info = await integration.connect_with_service_account(  # type: ignore[attr-defined]
      body.token,
      base_url=body.base_url,
      selected_repos=body.selected_repos,
      configured_by=str(current_user["id"]),
    )
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  return await _finish_service_account(integration_id, info, current_user)


@router.post("/{integration_id}/test", response_model=TestConnectionResult)
async def test_integration(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> TestConnectionResult:
  try:
    integration = registry.get(integration_id)
    user_id = current_user["id"]
    if integration_id == "jira":
      return await integration.test_connection(user_id=user_id)
    return await integration.test_connection()
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/disconnect", response_model=IntegrationInfo)
async def disconnect_integration(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  _require_admin_for_organization(integration_id, current_user)
  try:
    integration = registry.get(integration_id)
    user_id = current_user["id"]
    if integration_id == "jira":
      await integration.disconnect(user_id=user_id)
      return integration.get_info(user_id=user_id)
    await integration.disconnect()
    return integration.get_info()
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{integration_id}/projects")
async def get_projects(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> dict:
  if integration_id != "jira":
    raise HTTPException(status_code=501, detail="Projects endpoint is only available for Jira.")
  try:
    user_id = current_user["id"]
    projects = await registry.get("jira").get_projects(user_id=user_id)  # type: ignore[attr-defined]
    return {"projects": projects}
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{integration_id}/projects", response_model=IntegrationInfo)
async def update_projects(
  integration_id: str,
  body: SelectedProjectsRequest,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  if integration_id != "jira":
    raise HTTPException(status_code=501, detail="Projects endpoint is only available for Jira.")
  try:
    user_id = current_user["id"]
    info = await registry.get("jira").update_selected_projects(body.selected_projects, user_id=user_id)  # type: ignore[attr-defined]
    try:
      await sync_integration(integration_id, user_id=str(user_id))
    except Exception:
      pass
    return info
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jira/auto-select-project", response_model=IntegrationInfo)
async def auto_select_jira_project(
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  from app.core.storage import load_user_integration

  try:
    jira = registry.get("jira")
    user_id = current_user["id"]
    connection = load_user_integration(user_id, "jira") or {}
    site_url = str(connection.get("site_url") or "")
    if not site_url:
      raise ValueError("Jira is not connected or site URL is missing.")
    await jira.auto_select_projects_from_url(site_url, user_id=user_id)  # type: ignore[attr-defined]
    try:
      await sync_integration("jira", user_id=str(user_id))
    except Exception:
      pass
    return jira.get_info(user_id=user_id)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/issues")
async def get_issues(
  integration_id: str,
  jql: str | None = None,
  max_results: int = 50,
  current_user: dict = Depends(get_current_user),
) -> dict:
  if integration_id == "jira":
    try:
      user_id = current_user["id"]
      issues = await registry.get("jira").get_issues(jql=jql, max_results=max_results, user_id=user_id)  # type: ignore[attr-defined]
      return {"issues": issues}
    except KeyError as exc:
      raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
      raise HTTPException(status_code=400, detail=str(exc)) from exc

  if integration_id == "gitlab":
    try:
      issues = await registry.get("gitlab").get_issues(max_results=max_results)  # type: ignore[attr-defined]
      return {"issues": issues}
    except KeyError as exc:
      raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
      raise HTTPException(status_code=400, detail=str(exc)) from exc

  raise HTTPException(status_code=501, detail="Issues endpoint is only available for Jira and GitLab.")


@router.get("/{integration_id}/sprints")
async def get_sprints(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> dict:
  if integration_id != "jira":
    raise HTTPException(status_code=501, detail="Sprints endpoint is only available for Jira.")
  try:
    user_id = current_user["id"]
    sprints = await registry.get("jira").get_sprints(user_id=user_id)  # type: ignore[attr-defined]
    return {"sprints": sprints}
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/repositories")
async def get_repositories(integration_id: str) -> dict:
  try:
    integration = _require_git_hosting(integration_id)
    repos = await integration.get_repositories()  # type: ignore[attr-defined]
    return {"repositories": repos}
  except HTTPException:
    raise
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{integration_id}/repositories", response_model=IntegrationInfo)
async def update_repositories(
  integration_id: str,
  body: SelectedReposRequest,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  _require_admin_for_organization(integration_id, current_user)
  try:
    integration = _require_git_hosting(integration_id)
    info = await integration.update_selected_repos(body.selected_repos)  # type: ignore[attr-defined]
    try:
      await sync_integration(integration_id)
    except Exception:
      pass
    return info
  except HTTPException:
    raise
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/pull-requests")
async def get_pull_requests(integration_id: str, state: str = "all", max_results: int = 30) -> dict:
  try:
    integration = _require_git_hosting(integration_id)
    prs = await integration.get_pull_requests(state=state, max_results=max_results)  # type: ignore[attr-defined]
    return {"pull_requests": prs}
  except HTTPException:
    raise
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/commits")
async def get_commits(integration_id: str, max_results: int = 30) -> dict:
  try:
    integration = _require_git_hosting(integration_id)
    commits = await integration.get_commits(max_results=max_results)  # type: ignore[attr-defined]
    return {"commits": commits}
  except HTTPException:
    raise
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/files-changed")
async def get_files_changed(
  integration_id: str,
  pr_number: int,
  repo: str | None = None,
) -> dict:
  if integration_id not in GIT_HOSTING_IDS:
    raise HTTPException(status_code=501, detail="Files-changed endpoint is only available for GitHub and GitLab.")
  try:
    integration = registry.get(integration_id)
    files = await integration.get_files_changed(pr_number=pr_number, repo=repo)  # type: ignore[attr-defined]
    return {"files": files}
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{integration_id}/sync")
async def sync_integration_data(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> dict:
  try:
    user_id = str(current_user["id"]) if current_user and "id" in current_user else None
    return await sync_integration(integration_id, user_id=user_id)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/sync")
async def get_sync_cache(
  integration_id: str,
  current_user: dict = Depends(get_current_user),
) -> dict:
  user_id = str(current_user["id"]) if current_user and "id" in current_user else None
  cached = await load_sync_cache(integration_id, user_id=user_id)
  if not cached:
    raise HTTPException(status_code=404, detail="No sync cache yet. Connect and sync first.")
  return cached
