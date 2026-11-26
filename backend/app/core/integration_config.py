"""Jira OAuth config — .env plus local app settings. GitHub and GitLab have no OAuth: they use service accounts."""

from __future__ import annotations

from app.core.settings import get_settings
from app.core.storage import load_app_settings, save_app_settings


def _oauth_block(key: str) -> dict:
  app = load_app_settings()
  return dict(app.get(key) or {})


DEFAULT_JIRA_REDIRECT_URI = "http://127.0.0.1:6728/api/integrations/jira/callback"


def _first_set(*values: object) -> str:
  """The first value that is set, as trimmed text (empty when none is)."""
  return str(next((value for value in values if value), "")).strip()


def _source(local: dict, env_client_id: str | None) -> str:
  if local.get("client_id"):
    return "local"
  return "env" if env_client_id else "none"


def get_jira_oauth_config() -> dict[str, str]:
  settings = get_settings()
  jira = _oauth_block("jira_oauth")

  client_id = _first_set(jira.get("client_id"), settings.jira_client_id)
  client_secret = _first_set(jira.get("client_secret"), settings.jira_client_secret)
  redirect_uri = _first_set(jira.get("redirect_uri"), settings.jira_redirect_uri, DEFAULT_JIRA_REDIRECT_URI)

  return {
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": redirect_uri,
    "configured": bool(client_id and client_secret),
    "source": _source(jira, settings.jira_client_id),
  }


def _public_oauth(config: dict[str, str]) -> dict:
  client_id = config.get("client_id") or ""
  return {
    "configured": config.get("configured", False),
    "client_id": client_id[:8] + "…" if len(client_id) > 8 else client_id,
    "client_id_set": bool(client_id),
    "client_secret_set": bool(config.get("client_secret")),
    "redirect_uri": config.get("redirect_uri") or "",
    "source": config.get("source") or "none",
  }


def get_jira_oauth_public() -> dict:
  from app.integrations.jira.integration import JIRA_OAUTH_SCOPE_GUIDE, get_jira_oauth_scopes

  payload = _public_oauth(get_jira_oauth_config())
  payload["scopes"] = get_jira_oauth_scopes()
  payload["scope_guide"] = JIRA_OAUTH_SCOPE_GUIDE
  return payload


def save_jira_oauth_config(*, client_id: str, client_secret: str | None = None, redirect_uri: str | None = None) -> dict:
  return _save_oauth_block(
    "jira_oauth",
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    public_fn=get_jira_oauth_public,
  )


def _save_oauth_block(
  key: str,
  *,
  client_id: str,
  client_secret: str | None,
  redirect_uri: str | None,
  public_fn,
) -> dict:
  existing = _oauth_block(key)
  payload = {**existing, "client_id": client_id.strip()}
  if client_secret and client_secret.strip():
    payload["client_secret"] = client_secret.strip()
  if redirect_uri and redirect_uri.strip():
    payload["redirect_uri"] = redirect_uri.strip()
  save_app_settings({key: payload})
  return public_fn()
