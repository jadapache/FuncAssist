"""Integration OAuth config — .env plus local app settings."""

from __future__ import annotations

from app.core.settings import get_settings
from app.core.storage import load_app_settings, save_app_settings


def _oauth_block(key: str) -> dict:
  app = load_app_settings()
  return dict(app.get(key) or {})


def get_jira_oauth_config() -> dict[str, str]:
  settings = get_settings()
  jira = _oauth_block("jira_oauth")

  client_id = str(jira.get("client_id") or settings.jira_client_id or "").strip()
  client_secret = str(jira.get("client_secret") or settings.jira_client_secret or "").strip()
  redirect_uri = str(
    jira.get("redirect_uri") or settings.jira_redirect_uri or "http://127.0.0.1:6728/api/integrations/jira/callback"
  ).strip()

  return {
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": redirect_uri,
    "configured": bool(client_id and client_secret),
    "source": "local" if jira.get("client_id") else ("env" if settings.jira_client_id else "none"),
  }


def get_github_oauth_config() -> dict[str, str]:
  settings = get_settings()
  github = _oauth_block("github_oauth")

  client_id = str(github.get("client_id") or settings.github_client_id or "").strip()
  client_secret = str(github.get("client_secret") or settings.github_client_secret or "").strip()
  redirect_uri = str(
    github.get("redirect_uri") or settings.github_redirect_uri or "http://127.0.0.1:6728/api/integrations/github/callback"
  ).strip()

  return {
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": redirect_uri,
    "configured": bool(client_id and client_secret),
    "source": "local" if github.get("client_id") else ("env" if settings.github_client_id else "none"),
  }


def get_gitlab_oauth_config() -> dict[str, str]:
  settings = get_settings()
  gitlab = _oauth_block("gitlab_oauth")

  client_id = str(gitlab.get("client_id") or settings.gitlab_client_id or "").strip()
  client_secret = str(gitlab.get("client_secret") or settings.gitlab_client_secret or "").strip()
  base_url = str(gitlab.get("base_url") or settings.gitlab_base_url or "https://gitlab.com").strip().rstrip("/")
  redirect_uri = str(
    gitlab.get("redirect_uri") or settings.gitlab_redirect_uri or "http://127.0.0.1:6728/api/integrations/gitlab/callback"
  ).strip()

  return {
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": redirect_uri,
    "base_url": base_url,
    "configured": bool(client_id and client_secret),
    "source": "local" if gitlab.get("client_id") else ("env" if settings.gitlab_client_id else "none"),
  }


def _public_oauth(config: dict[str, str], *, include_base_url: bool = False) -> dict:
  client_id = config.get("client_id") or ""
  payload = {
    "configured": config.get("configured", False),
    "client_id": client_id[:8] + "…" if len(client_id) > 8 else client_id,
    "client_id_set": bool(client_id),
    "client_secret_set": bool(config.get("client_secret")),
    "redirect_uri": config.get("redirect_uri") or "",
    "source": config.get("source") or "none",
  }
  if include_base_url:
    payload["base_url"] = config.get("base_url") or "https://gitlab.com"
  return payload


def get_jira_oauth_public() -> dict:
  from app.integrations.jira.integration import JIRA_OAUTH_SCOPE_GUIDE, get_jira_oauth_scopes

  payload = _public_oauth(get_jira_oauth_config())
  payload["scopes"] = get_jira_oauth_scopes()
  payload["scope_guide"] = JIRA_OAUTH_SCOPE_GUIDE
  return payload


def get_github_oauth_public() -> dict:
  return _public_oauth(get_github_oauth_config())


def get_gitlab_oauth_public() -> dict:
  return _public_oauth(get_gitlab_oauth_config(), include_base_url=True)


def save_jira_oauth_config(*, client_id: str, client_secret: str | None = None, redirect_uri: str | None = None) -> dict:
  return _save_oauth_block(
    "jira_oauth",
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    public_fn=get_jira_oauth_public,
  )


def save_github_oauth_config(*, client_id: str, client_secret: str | None = None, redirect_uri: str | None = None) -> dict:
  return _save_oauth_block(
    "github_oauth",
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    public_fn=get_github_oauth_public,
  )


def save_gitlab_oauth_config(
  *,
  client_id: str,
  client_secret: str | None = None,
  redirect_uri: str | None = None,
  base_url: str | None = None,
) -> dict:
  return _save_oauth_block(
    "gitlab_oauth",
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    base_url=base_url,
    public_fn=get_gitlab_oauth_public,
  )


def _save_oauth_block(
  key: str,
  *,
  client_id: str,
  client_secret: str | None,
  redirect_uri: str | None,
  public_fn,
  base_url: str | None = None,
) -> dict:
  existing = _oauth_block(key)
  payload = {**existing, "client_id": client_id.strip()}
  if client_secret and client_secret.strip():
    payload["client_secret"] = client_secret.strip()
  if redirect_uri and redirect_uri.strip():
    payload["redirect_uri"] = redirect_uri.strip()
  if base_url and base_url.strip():
    payload["base_url"] = base_url.strip().rstrip("/")
  save_app_settings({key: payload})
  return public_fn()
