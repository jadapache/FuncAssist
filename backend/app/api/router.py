from fastapi import APIRouter

from app.api import (
  auth,
  document_agent,
  features,
  history,
  integrations,
  knowledge,
  settings as settings_api,
  transcription,
  transcription_stream,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(integrations.router)
api_router.include_router(settings_api.router)
api_router.include_router(knowledge.router)
api_router.include_router(features.router)
api_router.include_router(history.router)
api_router.include_router(document_agent.router)
api_router.include_router(transcription.router)
api_router.include_router(transcription_stream.router)




