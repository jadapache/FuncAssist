from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai.templates import ensure_ai_files
from app.api.router import api_router
from app.api.settings import health_router
from app.context.knowledge import ensure_knowledge_dirs
from app.core.settings import ROOT_DIR, ensure_local_dirs, get_settings

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
  import asyncio
  from app.api.transcription_stream import set_main_loop

  set_main_loop(asyncio.get_running_loop())
  ensure_local_dirs()
  ensure_knowledge_dirs()
  ensure_ai_files()
  yield


def create_app() -> FastAPI:
  settings = get_settings()

  app = FastAPI(
    title="QA Project MGMT",
    description="Local PM + QA command center with grounded AI.",
    version="0.2.0",
    lifespan=lifespan,
  )

  app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )

  app.include_router(health_router)
  app.include_router(api_router)

  if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
      app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str = ""):
      candidate = FRONTEND_DIST / full_path
      if full_path and candidate.is_file():
        return FileResponse(candidate)
      return FileResponse(FRONTEND_DIST / "index.html")

  return app


app = create_app()
