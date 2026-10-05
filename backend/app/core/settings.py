import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]
_custom_local = os.getenv("DATA_DIR") or os.getenv("LOCAL_DIR")
LOCAL_DIR = Path(_custom_local) if _custom_local else ROOT_DIR / "local"
CONNECTIONS_DIR = LOCAL_DIR / "connections"
CACHE_DIR = LOCAL_DIR / "cache"
SETTINGS_DIR = LOCAL_DIR / "settings"
HISTORY_DIR = LOCAL_DIR / "history"


class Settings(BaseSettings):
  model_config = SettingsConfigDict(
    env_file=str(ROOT_DIR / ".env"),
    env_file_encoding="utf-8",
    extra="ignore",
  )

  pmqa_host: str = "127.0.0.1"
  pmqa_port: int = 8000
  pmqa_frontend_url: str = "http://127.0.0.1:5173"
  pmqa_backend_url: str = "http://127.0.0.1:8000"
  pmqa_secret_key: str | None = None

  jira_client_id: str = ""
  jira_client_secret: str = ""
  jira_redirect_uri: str = "http://127.0.0.1:8000/api/integrations/jira/callback"
  jira_oauth_extra_scopes: str = ""

  github_client_id: str = ""
  github_client_secret: str = ""
  github_redirect_uri: str = "http://127.0.0.1:8000/api/integrations/github/callback"

  gitlab_client_id: str = ""
  gitlab_client_secret: str = ""
  gitlab_redirect_uri: str = "http://127.0.0.1:8000/api/integrations/gitlab/callback"
  gitlab_base_url: str = "https://gitlab.com"

  @property
  def cors_origins(self) -> list[str]:
    origins = {
      self.pmqa_frontend_url.rstrip("/"),
      self.pmqa_backend_url.rstrip("/"),
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://localhost:8000",
      "http://127.0.0.1:8000",
    }
    return [origin for origin in origins if origin]


@lru_cache
def get_settings() -> Settings:
  return Settings()


def ensure_local_dirs() -> None:
  for path in (LOCAL_DIR, CONNECTIONS_DIR, CACHE_DIR, SETTINGS_DIR, HISTORY_DIR):
    path.mkdir(parents=True, exist_ok=True)
