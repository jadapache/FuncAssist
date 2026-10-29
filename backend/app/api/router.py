from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

from app.api import (
  auth,
  document_agent,
  drafts,
  history,
  integrations,
  knowledge,
  me,
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
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(me.router, prefix="/me")
api_router.include_router(me.router, prefix="/v1/me")
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


@api_router.post("/runs/{run_id}/cancel")
async def cancel_run_alias(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await document_agent.cancel_agent_run(run_id)
