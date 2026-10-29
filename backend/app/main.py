
import os
import sys

if sys.platform == "win32":
  import asyncio
  asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Prevent LiteLLM from attempting synchronous remote fetches during startup/imports
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


from contextlib import asynccontextmanager
from fastapi import FastAPI
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

  try:
    yield
  finally:
    refresher_task.cancel()
    try:
      await refresher_task
    except (asyncio.CancelledError, Exception):
      pass
    await close_redis_client()


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
  app.include_router(me_router, prefix="/v1/me")
  app.include_router(api_router)

  if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
      app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = ""):
      candidate = FRONTEND_DIST / full_path
      if full_path and candidate.is_file():
        return FileResponse(candidate)
      return FileResponse(FRONTEND_DIST / "index.html")

  return app


app = create_app()