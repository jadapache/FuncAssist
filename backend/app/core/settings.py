import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


def _get_user_data_dir() -> Path:
  """
  Returns the OS-standard user application data directory.
  Precedence: DATA_DIR env var > LOCAL_DIR env var > platform default.
  """
  env_override = os.getenv("DATA_DIR") or os.getenv("LOCAL_DIR")
  if env_override:
    return Path(env_override)

  app_name = "qa-project-mgmt"

  if sys.platform == "win32":
    local_app_data = os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    return Path(local_app_data) / app_name

  if sys.platform == "darwin":
    return Path.home() / "Library" / "Application Support" / app_name

  # Linux and other Unix
  xdg_data_home = os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
  return Path(xdg_data_home) / app_name


# Primary path constants
USER_DATA_DIR = _get_user_data_dir()
LOCAL_DIR = USER_DATA_DIR  # backward-compatible alias
SETTINGS_DIR = USER_DATA_DIR / "settings"
CONNECTIONS_DIR = USER_DATA_DIR / "connections"
CACHE_DIR = USER_DATA_DIR / "cache"
HISTORY_DIR = USER_DATA_DIR / "history"
MODELS_DIR = USER_DATA_DIR / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
BUILTIN_MODELS_DIR = MODELS_DIR / "builtin"


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
  for path in (
    USER_DATA_DIR,
    SETTINGS_DIR,
    CONNECTIONS_DIR,
    CACHE_DIR,
    HISTORY_DIR,
    MODELS_DIR,
    WHISPER_MODELS_DIR,
    BUILTIN_MODELS_DIR,
  ):
    path.mkdir(parents=True, exist_ok=True)
