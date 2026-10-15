import os
import sys

# Prevent LiteLLM from attempting synchronous remote fetches during startup/imports
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from functools import lru_cache
from pathlib import Path
from typing import Any

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

  app_name = "funcassist"

  if sys.platform == "win32":
    local_app_data = os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    return Path(local_app_data) / app_name

  if sys.platform == "darwin":
    return Path.home() / "Library" / "Application Support" / app_name

  # Linux and other Unix
  xdg_data_home = os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
  return Path(xdg_data_home) / app_name


def _get_user_documents_dir() -> Path:
  """
  Returns the user's Documents folder under 'FuncAssist'.
  Precedence: DOCUMENTS_DIR env var > OS Documents / 'FuncAssist'.
  """
  folder_name = "FuncAssist"

  env_override = os.getenv("DOCUMENTS_DIR")
  if env_override:
    return Path(env_override) / folder_name

  if sys.platform == "win32":
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
      return Path(user_profile) / "Documents" / folder_name

  return Path.home() / "Documents" / folder_name


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
GENERATED_DIR = USER_DATA_DIR / "generated"
GENERATED_INDEX_FILE = GENERATED_DIR / "generated_index.json"

# App-internal state paths (active jobs, local index)
APP_TRANSCRIPTIONS_DIR = USER_DATA_DIR / "transcriptions"
ACTIVE_JOBS_DIR = APP_TRANSCRIPTIONS_DIR / "active_jobs"
TRANSCRIPTIONS_INDEX_FILE = APP_TRANSCRIPTIONS_DIR / "transcriptions_index.json"

# Accessible user documents paths
USER_DOCUMENTS_DIR = _get_user_documents_dir()
USER_TRANSCRIPTIONS_DIR = USER_DOCUMENTS_DIR / "Transcripciones"
USER_DRAFTS_DIR = USER_DOCUMENTS_DIR / "Borradores"


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
  cors_origins_str: str = ""

  # Database Connection
  database_url: str | None = None

  def get_database_url(self, for_sqlalchemy: bool = False) -> str | None:
    """Return configured PostgreSQL connection URL.
    
    If for_sqlalchemy is True, ensures the URL dialect is postgresql+psycopg://.
    """
    url = self.database_url or os.getenv("DATABASE_URL")
    if url and url.strip():
      clean_url = url.strip()
      if for_sqlalchemy:
        if clean_url.startswith("postgresql://"):
          clean_url = "postgresql+psycopg://" + clean_url[len("postgresql://"):]
        elif clean_url.startswith("postgres://"):
          clean_url = "postgresql+psycopg://" + clean_url[len("postgres://"):]
      return clean_url
    return None

  def get_knowledge_db_url(self) -> str | None:
    return self.get_database_url(for_sqlalchemy=False)

  def get_database_params(self) -> dict[str, Any]:
    """Parse connection parameters from database_url if needed."""
    url = self.get_database_url(for_sqlalchemy=False)
    if not url:
      return {
        "host": "",
        "port": 5432,
        "user": "",
        "password": "",
        "database": "",
      }
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return {
      "host": parsed.hostname or "",
      "port": parsed.port or 5432,
      "user": parsed.username or "",
      "password": parsed.password or "",
      "database": (parsed.path or "").lstrip("/"),
    }

  def get_knowledge_db_params(self) -> dict[str, Any]:
    return self.get_database_params()

  @property
  def cors_origins(self) -> list[str]:
    if self.cors_origins_str.strip() == "*":
      return ["*"]
    origins = {
      self.pmqa_frontend_url.rstrip("/"),
      self.pmqa_backend_url.rstrip("/"),
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://localhost:8000",
      "http://127.0.0.1:8000",
    }
    if self.cors_origins_str:
      for o in self.cors_origins_str.split(","):
        cleaned = o.strip().rstrip("/")
        if cleaned:
          origins.add(cleaned)
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
    APP_TRANSCRIPTIONS_DIR,
    ACTIVE_JOBS_DIR,
    GENERATED_DIR,
    USER_DOCUMENTS_DIR,
    USER_TRANSCRIPTIONS_DIR,
    USER_DRAFTS_DIR,
    USER_DRAFTS_DIR / "Mejoras",
    USER_DRAFTS_DIR / "Levantamiento",
    USER_DRAFTS_DIR / "Inventario",
  ):
    path.mkdir(parents=True, exist_ok=True)
