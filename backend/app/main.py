
import os
import sys

if sys.platform == "win32":
  import asyncio
  asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Prevent LiteLLM from attempting synchronous remote fetches during startup/imports
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai.templates import ensure_ai_files
from app.api.me import router as me_router
from app.api.router import api_router
from app.api.settings import health_router
from app.context.knowledge import ensure_knowledge_dirs
from app.core.settings import ROOT_DIR, ensure_local_dirs, get_settings

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


async def _preload_local_voice_model() -> None:
  """Warm up the configured local voice model without blocking app startup."""
  import asyncio
  from app.core.storage import load_app_settings

  try:
    ai_cfg = load_app_settings().get("ai", {})
    provider = (ai_cfg.get("transcription_provider") or "auto").lower()
    has_cloud_credentials = bool(
      ai_cfg.get("transcription_groq_api_key")
      or ai_cfg.get("transcription_openai_api_key")
      or os.getenv("GROQ_API_KEY")
      or os.getenv("OPENAI_API_KEY")
    )
    if provider not in ("auto", "local", "builtin"):
      return
    if provider == "auto" and has_cloud_credentials:
      return

    model_id = (ai_cfg.get("transcription_model") or "base").strip()
    clean_id = (
      model_id.replace("whisper-", "")
      .replace("faster-whisper-", "")
      .replace("fw-", "")
      .strip()
    ) or "base"

    # This warm-up targets the openai-whisper local provider. Other local
    # engines (ONNX/Faster-Whisper/Moonshine) have their own download/lifecycle
    # controls and should not be forced through the .pt loader.
    if any(marker in model_id.lower() for marker in ("onnx", "faster-whisper", "fw-", "moonshine", "parakeet", "sense-voice")):
      return

    from app.features.transcription.whisper_local import (
      download_model_file,
      get_whisper_cache_dir,
      prepare_whisper_download,
      preload_local_whisper_model,
    )

    # Register the download so the existing FloatingJobToast can show only
    # model preparation progress, never the short dictation request itself.
    model_file = get_whisper_cache_dir() / f"{clean_id}.pt"
    if not model_file.exists() or model_file.stat().st_size <= 1024 * 1024:
      prepare_whisper_download(clean_id)
    await asyncio.to_thread(download_model_file, clean_id)
    await asyncio.to_thread(preload_local_whisper_model, clean_id)
  except Exception:
    # Voice dictation remains available through the normal lazy-loading path.
    import logging
    logging.getLogger(__name__).exception("Local voice model preload failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
  import asyncio
  from app.api.transcription_stream import set_main_loop
  from app.core.index_refresher import run_index_refresher

  loop = asyncio.get_running_loop()
  set_main_loop(loop)
  ensure_local_dirs()
  from app.context.knowledge_migration import migrate_knowledge_if_needed
  from app.db.database import init_db

  await init_db()
  from app.core.redis import close_redis_client, init_redis
  await init_redis()
  from app.core.integration_migration import migrate_integrations_schema_if_needed
  migrate_integrations_schema_if_needed()
  migrate_knowledge_if_needed()
  ensure_knowledge_dirs()
  ensure_ai_files()

  refresher_task = asyncio.create_task(run_index_refresher())
  voice_model_task = asyncio.create_task(_preload_local_voice_model())

  try:
    yield
  finally:
    refresher_task.cancel()
    voice_model_task.cancel()
    try:
      await refresher_task
    except (asyncio.CancelledError, Exception):
      pass
    try:
      await voice_model_task
    except (asyncio.CancelledError, Exception):
      pass
    await close_redis_client()


TAGS_METADATA = [
    {"name": "auth", "description": "Autenticación de usuarios y solicitudes de acceso."},
    {"name": "user", "description": "Perfil de usuario y administración de usuarios."},
    {"name": "me-configuration", "description": "Preferencias de usuario, credenciales BYOK e integraciones personales."},
    {"name": "chat", "description": "Sesiones de chat y mensajes interactivos."},
    {"name": "document-agent", "description": "Agente conversacional y generación de documentos."},
    {"name": "pm-features", "description": "Herramientas de IA para Product Managers (Standup, PRD, etc.)."},
    {"name": "qa-features", "description": "Herramientas de IA para Aseguramiento de Calidad (QA)."},
    {"name": "doc-features", "description": "Generación de documentos funcionales (Mejoras, Inventario, Levantamiento)."},
    {"name": "drafts", "description": "Gestión de borradores de documentos."},
    {"name": "history", "description": "Historial de generación de artefactos y documentos."},
    {"name": "knowledge", "description": "Base de conocimientos y recuperación RAG."},
    {"name": "transcription", "description": "Transcripción de audio y progreso en tiempo real."},
    {"name": "integrations", "description": "Integraciones externas (Jira, GitHub, GitLab)."},
    {"name": "ai-settings", "description": "Catálogo de modelos y configuración de enrutamiento IA."},
    {"name": "ai-management", "description": "Gestión de modelos locales (Ollama, Whisper, Built-in)."},
    {"name": "ai-templates", "description": "Plantillas de prompts, rúbricas y logs de IA."},
    {"name": "templates", "description": "Gestión de plantillas de documentos."},
    {"name": "settings", "description": "Configuraciones globales del sistema y base de datos."},
    {"name": "health", "description": "Monitoreo y estado de salud de la aplicación."},
]


def create_app() -> FastAPI:
  settings = get_settings()
  secret = settings.secret_key or os.getenv("SECRET_KEY")
  if not secret or not secret.strip():
    raise RuntimeError("SECRET_KEY environment variable is required to start the application")

  salt = settings.pbkdf2_salt or os.getenv("PBKDF2_SALT")
  if not salt or not salt.strip():
    raise RuntimeError("PBKDF2_SALT environment variable is required to start the application")

  app = FastAPI(
    title="FuncAssist API",
    description="FuncAssist - Functional Analysis & Requirements Assistant.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=TAGS_METADATA,
    swagger_ui_parameters={"persistAuthorization": True},
  )

  app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )

  app.include_router(health_router)
  app.include_router(me_router, prefix="/v1/me", include_in_schema=False)
  app.include_router(api_router)

  if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
      app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = ""):
      if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
      candidate = FRONTEND_DIST / full_path
      if full_path and candidate.is_file():
        return FileResponse(candidate)
      return FileResponse(FRONTEND_DIST / "index.html")

  return app


app = create_app()
