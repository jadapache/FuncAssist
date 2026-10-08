from fastapi import APIRouter

from app.api import (
  document_agent,
  drafts,
  history,
  integrations,
  knowledge,
  settings as settings_api,
  transcription,
  transcription_stream,
  user,
)
from app.api.routers import (
  ai_management,
  ai_settings,
  ai_templates,
  features_doc,
  features_pm,
  features_qa,
  templates,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(user.router)
api_router.include_router(integrations.router)
api_router.include_router(settings_api.router)
api_router.include_router(knowledge.router)
api_router.include_router(history.router)
api_router.include_router(document_agent.router)
api_router.include_router(drafts.router)
api_router.include_router(transcription.router)
api_router.include_router(transcription_stream.router)
api_router.include_router(ai_settings.router)
api_router.include_router(ai_management.router)
api_router.include_router(ai_templates.router)
api_router.include_router(features_pm.router)
api_router.include_router(features_qa.router)
api_router.include_router(features_doc.router)
api_router.include_router(templates.router)
