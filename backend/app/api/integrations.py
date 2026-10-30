from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.settings import get_settings
from app.integrations.base import AuthMethod, IntegrationInfo, TestConnectionResult
from app.integrations.registry import GIT_HOSTING_IDS, registry
from app.integrations.sync import load_sync_cache, sync_integration

router = APIRouter(
  prefix="/integrations",
  tags=["integrations"],
  dependencies=[Depends(get_current_user)],
)


def _require_git_hosting(integration_id: str):
  if integration_id not in GIT_HOSTING_IDS:
    raise HTTPException(
      status_code=501,
      detail="Repositories endpoint is only available for GitHub and GitLab.",
    )
  return registry.get(integration_id)


class PatConnectRequest(BaseModel):
  token: str = Field(min_length=1)
  email: str | None = None
  base_url: str | None = None
  selected_repos: list[str] = Field(default_factory=list)


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
    "methods": [AuthMethod.OAUTH.value, AuthMethod.PERSONAL_ACCESS_TOKEN.value],
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
    await registry.get("jira").handle_oauth_callback(code, state)
    await sync_integration("jira")
  except Exception as exc:
    return RedirectResponse(f"{frontend}/integrations?jira=error&message={quote(str(exc))}")

  return RedirectResponse(f"{frontend}/integrations?jira=connected")


@router.get("/github/callback")
async def github_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
  settings = get_settings()
  frontend = settings.frontend_url.rstrip("/")

  if error:
    return RedirectResponse(f"{frontend}/integrations?github=error&message={quote(error)}")
  if not code or not state:
    return RedirectResponse(f"{frontend}/integrations?github=error&message=missing_code")

  try:
    await registry.get("github").handle_oauth_callback(code, state)
    await sync_integration("github")
  except Exception as exc:
    return RedirectResponse(f"{frontend}/integrations?github=error&message={quote(str(exc))}")

  return RedirectResponse(f"{frontend}/integrations?github=connected")


@router.get("/gitlab/callback")
async def gitlab_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
  settings = get_settings()
  frontend = settings.frontend_url.rstrip("/")

  if error:
    return RedirectResponse(f"{frontend}/integrations?gitlab=error&message={quote(error)}")
  if not code or not state:
    return RedirectResponse(f"{frontend}/integrations?gitlab=error&message=missing_code")

  try:
    await registry.get("gitlab").handle_oauth_callback(code, state)
    await sync_integration("gitlab")
  except Exception as exc:
    return RedirectResponse(f"{frontend}/integrations?gitlab=error&message={quote(str(exc))}")

  return RedirectResponse(f"{frontend}/integrations?gitlab=connected")


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
  try:
    integration = registry.get(integration_id)
    user_id = current_user["id"]
    if integration_id == "jira":
      result = await integration.start_oauth(user_id=user_id)
    else:
      result = await integration.start_oauth()
    return result.model_dump()
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except NotImplementedError as exc:
    raise HTTPException(status_code=501, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{integration_id}/pat", response_model=IntegrationInfo)
async def connect_with_pat(
  integration_id: str,
  body: PatConnectRequest,
  current_user: dict = Depends(get_current_user),
) -> IntegrationInfo:
  try:
    integration = registry.get(integration_id)
    user_id = current_user["id"]
    info = await integration.connect_with_pat(
      body.token,
      email=body.email,
      base_url=body.base_url,
      selected_repos=body.selected_repos,
    )
    if await integration.authenticate(user_id=user_id if integration_id == "jira" else None):
      try:
        await sync_integration(integration_id)
      except Exception:
        pass
    return info
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


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
      await sync_integration(integration_id)
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
      await sync_integration("jira")
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
async def update_repositories(integration_id: str, body: SelectedReposRequest) -> IntegrationInfo:
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
