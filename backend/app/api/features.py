from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.core.template_storage import (
  delete_template,
  get_template_detail,
  list_templates,
  save_template_file,
  update_template_metadata,
)

from app.ai.catalog import get_model_catalog
from app.ai.logging import list_logs
from app.ai.providers.base import AIMessage
from app.ai.providers.factory import get_ai_settings, resolve_provider
from app.ai.runner import run_grounded_feature
from app.ai.templates import (
  get_prompt,
  get_rubric,
  list_prompts,
  list_rubrics,
  reset_prompt,
  reset_rubric,
  save_prompt,
  save_rubric,
)
from app.api.deps import (
  get_chat_repository,
  get_prd_repository,
  get_standup_repository,
  get_test_plan_repository,
)
from app.api.middleware.error_handlers import handle_grounded_errors
from app.core.storage import load_app_settings, save_app_settings
from app.db.interfaces import (
  IChatRepository,
  IPRDRepository,
  IStandupRepository,
  ITestPlanRepository,
)
from app.features.standup.service import generate_standup



router = APIRouter(tags=["ai"])


class AISettingsUpdate(BaseModel):
  provider: str | None = None
  model: str | None = None
  transcription_provider: str | None = None
  transcription_model: str | None = None
  voice_command_provider: str | None = None
  voice_command_model: str | None = None
  openai_api_key: str | None = None
  claude_api_key: str | None = None
  groq_api_key: str | None = None
  gemini_api_key: str | None = None
  transcription_groq_api_key: str | None = None
  transcription_openai_api_key: str | None = None
  ollama_base_url: str | None = None


AISettingsUpdate.model_rebuild()


class OllamaPullRequest(BaseModel):
  name: str = Field(min_length=1)
  base_url: str | None = None


OllamaPullRequest.model_rebuild()


class GroundedRequest(BaseModel):
  query: str = "Generate standup from recent work."
  sources: list[str] | None = None
  document_ids: list[str] | None = None
  chat_context: str | None = None


GroundedRequest.model_rebuild()


class FeatureWorkspaceRequest(BaseModel):
  query: str = Field(min_length=1)
  sources: list[str] | None = None
  document_ids: list[str] = Field(default_factory=list)
  chat_context: str | None = None


FeatureWorkspaceRequest.model_rebuild()


class TemplateUpdate(BaseModel):
  model_config = ConfigDict(extra="allow")
  system: str | None = None
  user_template: str | None = None
  allowed_sources: list[str] | None = None


TemplateUpdate.model_rebuild()


class RubricUpdate(BaseModel):
  model_config = ConfigDict(extra="allow")
  criteria: list[str]


RubricUpdate.model_rebuild()


@router.get("/ai/models/catalog")
async def ai_models_catalog(
    refresh: bool = False,
    provider: str = "all",
    task_type: str = "all",
) -> dict[str, Any]:
  catalog = await get_model_catalog(refresh=refresh, provider=provider, task_type=task_type)
  return catalog.model_dump()


@router.get("/ai/settings")
async def ai_settings() -> dict[str, Any]:
  """Get current AI configuration"""
  import os
  from app.ai.providers.registry import find_provider_spec

  config = get_ai_settings()
  provider = (config.get("provider") or "").lower()
  spec = find_provider_spec(provider)
  active_key_set = False
  if spec:
    if spec.is_local:
      active_key_set = bool(config.get("ollama_base_url"))
    elif spec.config_key:
      active_key_set = bool(config.get(spec.config_key) or (spec.env_key and os.getenv(spec.env_key)))
    elif spec.env_key:
      active_key_set = bool(os.getenv(spec.env_key))

  return {
    "provider": config.get("provider") or None,
    "model": config.get("model") or None,
    "transcription_provider": config.get("transcription_provider") or None,
    "transcription_model": config.get("transcription_model") or None,
    "voice_command_provider": config.get("voice_command_provider") or None,
    "voice_command_model": config.get("voice_command_model") or None,
    "openai_api_key_set": bool(config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")),
    "claude_api_key_set": bool(config.get("claude_api_key") or os.getenv("ANTHROPIC_API_KEY")),
    "groq_api_key_set": bool(config.get("groq_api_key") or os.getenv("GROQ_API_KEY")),
    "gemini_api_key_set": bool(config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")),
    "transcription_groq_api_key_set": bool(
      config.get("transcription_groq_api_key") or config.get("groq_api_key") or os.getenv("GROQ_API_KEY")
    ),
    "transcription_openai_api_key_set": bool(
      config.get("transcription_openai_api_key") or config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    ),
    "ollama_base_url": config.get("ollama_base_url"),
    "active_api_key_set": active_key_set,
  }


@router.put("/ai/settings")
async def update_ai_settings(body: AISettingsUpdate) -> dict[str, Any]:
  """Update AI settings - merges new values with existing ones"""
  current = load_app_settings()
  ai = dict(current.get("ai") or {})
  
  # Merge new values into existing AI settings
  for key, value in body.model_dump(exclude_none=True).items():
    if value is not None:  # Only update non-None values
      ai[key] = value
  
  # Save merged settings
  save_app_settings({"ai": ai})
  
  return await ai_settings()



class AITestConnectionRequest(BaseModel):
  provider: str | None = None
  model: str | None = None
  api_key: str | None = None
  ollama_base_url: str | None = None


AITestConnectionRequest.model_rebuild()


@router.post("/ai/test-connection")
async def test_ai_connection(body: AITestConnectionRequest) -> dict[str, Any]:
  config = get_ai_settings()
  provider_name = (body.provider or config.get("provider") or "").lower()
  model_name = (body.model or config.get("model") or "").strip()
  if not provider_name:
    return {
      "ok": False,
      "message": "No hay ningún proveedor de IA configurado en el sistema.",
    }
  if not model_name:
    return {
      "ok": False,
      "message": f"No hay un modelo especificado para el proveedor '{provider_name}'.",
    }

  test_messages = [AIMessage(role="user", content="Hola, responde únicamente con la palabra 'OK'.")]

  try:
    p = resolve_provider(
      provider_name=provider_name,
      model_name=model_name,
      api_key=body.api_key,
      base_url=body.ollama_base_url,
    )
    res = await p.complete(test_messages, model=model_name, max_tokens=100)

    return {
      "ok": True,
      "message": f"Conexión exitosa con {provider_name} ({model_name}).",
      "response": res.text,
      "provider": provider_name,
      "model": model_name,
    }
  except Exception as e:
    return {
      "ok": False,
      "message": f"Error al probar conexión con {provider_name} ({model_name}): {e}",
      "provider": provider_name,
      "model": model_name,
    }


@router.get("/ai/ollama/models")
async def list_ollama_models(base_url: str | None = None) -> dict[str, Any]:
  config = get_ai_settings()
  target_url = (base_url or config.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
  try:
    async with httpx.AsyncClient(timeout=8.0) as client:
      res = await client.get(f"{target_url}/api/tags")
      res.raise_for_status()
      data = res.json()
      models = [m.get("name") for m in data.get("models", []) if m.get("name")]
      return {"online": True, "models": models}
  except Exception as e:
    return {"online": False, "models": [], "error": str(e)}


@router.post("/ai/ollama/pull")
async def pull_ollama_model(body: OllamaPullRequest) -> dict[str, Any]:
  config = get_ai_settings()
  target_url = (body.base_url or config.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
  try:
    async with httpx.AsyncClient(timeout=600.0) as client:
      res = await client.post(f"{target_url}/api/pull", json={"name": body.name, "stream": False})
      res.raise_for_status()
      return {"status": "success", "model": body.name, "response": res.json()}
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error al descargar el modelo {body.name} en Ollama: {e}")


@router.delete("/ai/ollama/{model_name:path}")
async def delete_ollama_model_endpoint(model_name: str, base_url: str | None = None) -> dict[str, Any]:
  """Delete a local Ollama model to free disk space."""
  config = get_ai_settings()
  target_url = (base_url or config.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
  try:
    async with httpx.AsyncClient(timeout=30.0) as client:
      req = client.build_request("DELETE", f"{target_url}/api/delete", json={"name": model_name})
      res = await client.send(req)
      res.raise_for_status()
      return {"ok": True, "model": model_name, "message": f"Modelo {model_name} eliminado de Ollama correctamente."}
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error al eliminar el modelo {model_name} en Ollama: {e}")



@router.get("/ai/whisper/models")
async def list_whisper_models() -> dict[str, Any]:
  """List all local Whisper built-in models and their download status on disk."""
  from app.features.transcription.whisper_local import get_local_models_info
  models = get_local_models_info()
  return {"ok": True, "models": models}


@router.post("/ai/whisper/download/{model_id}")
async def download_whisper_model_endpoint(model_id: str) -> dict[str, Any]:
  """Download a local Whisper model to disk cache."""
  import asyncio
  from app.features.transcription.whisper_local import download_model_file
  try:
    clean_id = model_id.replace("whisper-", "")
    path = await asyncio.to_thread(download_model_file, clean_id)
    return {
      "ok": True,
      "model_id": clean_id,
      "file_path": str(path),
      "message": f"Modelo {clean_id} descargado y listo para uso local.",
    }
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error descargando modelo Whisper {model_id}: {exc}") from exc


@router.delete("/ai/whisper/{model_id}")
async def delete_whisper_model_endpoint(model_id: str) -> dict[str, Any]:
  """Delete a downloaded local Whisper model from disk to free space."""
  from app.features.transcription.whisper_local import delete_model_file
  try:
    clean_id = model_id.replace("whisper-", "")
    deleted = delete_model_file(clean_id)
    if not deleted:
      return {"ok": True, "message": f"El modelo {clean_id} no estaba descargado."}
    return {"ok": True, "message": f"Modelo Whisper {clean_id} eliminado del disco con éxito."}
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Error eliminando modelo Whisper {model_id}: {exc}") from exc


@router.get("/ai/prompts")
async def prompts() -> dict[str, Any]:
  return {"prompts": list_prompts()}


@router.get("/ai/prompts/{feature}")
async def prompt_detail(feature: str) -> dict[str, Any]:
  try:
    return get_prompt(feature)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/ai/prompts/{feature}")
async def update_prompt(feature: str, body: TemplateUpdate) -> dict[str, Any]:
  try:
    return save_prompt(feature, body.model_dump(exclude_none=True))
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai/prompts/{feature}/reset")
async def reset_prompt_endpoint(feature: str) -> dict[str, Any]:
  try:
    return reset_prompt(feature)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ai/rubrics")
async def rubrics() -> dict[str, Any]:
  return {"rubrics": list_rubrics()}


@router.get("/ai/rubrics/{feature}")
async def rubric_detail(feature: str) -> dict[str, Any]:
  try:
    return get_rubric(feature)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/ai/rubrics/{feature}")
async def update_rubric(feature: str, body: RubricUpdate) -> dict[str, Any]:
  try:
    return save_rubric(feature, body.model_dump())
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai/rubrics/{feature}/reset")
async def reset_rubric_endpoint(feature: str) -> dict[str, Any]:
  try:
    return reset_rubric(feature)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ai/logs")
async def ai_logs(limit: int = 20) -> dict[str, Any]:
  return {"logs": list_logs(limit=limit)}


@router.post("/features/standup")
@handle_grounded_errors
async def standup(
  body: GroundedRequest = GroundedRequest(),
  standup_repo: IStandupRepository = Depends(get_standup_repository),
) -> dict[str, Any]:
  res = await generate_standup(body.query)
  if isinstance(res, dict) and "markdown" in res:
    await standup_repo.create_standup(
      title=f"Standup {res.get('date', '')}".strip(),
      content=res["markdown"],
      sources=body.sources or [],
    )
  return res


@router.post("/features/ask")
@handle_grounded_errors
async def ask_product(
  body: GroundedRequest,
  chat_repo: IChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
  if not body.query.strip():
    raise HTTPException(status_code=400, detail="Query is required.")
  res = await run_grounded_feature(
    feature="ask_product",
    query=body.query,
    sources=body.sources,
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )
  if isinstance(res, dict) and "markdown" in res:
    await chat_repo.save_message(
      session_id="default",
      role="user",
      content=body.query,
    )
    await chat_repo.save_message(
      session_id="default",
      role="assistant",
      content=res["markdown"],
      context_sources=res.get("context_sources") or [],
    )
  return res


@router.post("/features/prd-checker")
@handle_grounded_errors
async def prd_checker(
  body: FeatureWorkspaceRequest,
  prd_repo: IPRDRepository = Depends(get_prd_repository),
) -> dict[str, Any]:
  if not body.document_ids:
    raise HTTPException(status_code=400, detail="Upload at least one PRD or spec file.")
  res = await run_grounded_feature(
    feature="prd_checker",
    query=body.query,
    sources=body.sources or ["knowledge"],
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )
  if isinstance(res, dict) and "markdown" in res:
    await prd_repo.create_prd_review(
      prd_title="Auditoría PRD",
      content=res["markdown"],
    )
  return res


@router.post("/features/change-impact")
@handle_grounded_errors
async def change_impact(body: FeatureWorkspaceRequest) -> dict[str, Any]:
  sources = body.sources or []
  if not body.document_ids and not sources:
    raise HTTPException(
      status_code=400,
      detail="Upload files and/or enable live sources (Jira, GitHub, GitLab).",
    )
  return await run_grounded_feature(
    feature="change_impact",
    query=body.query,
    sources=body.sources or ["jira", "github", "knowledge"],
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )


QA_FEATURE_KEYS = {
  "regression",
  "api_qa",
  "visual_qa",
  "smart_test_data",
  "release_readiness",
}

QA_DEFAULT_SOURCES: dict[str, list[str]] = {
  "regression": ["jira", "github", "gitlab", "knowledge"],
  "api_qa": ["knowledge", "github", "gitlab"],
  "visual_qa": ["knowledge", "jira"],
  "smart_test_data": ["knowledge"],
  "release_readiness": ["jira", "github", "gitlab", "knowledge"],
}


@router.post("/features/qa/{feature_key}")
@handle_grounded_errors
async def qa_feature(
  feature_key: str,
  body: FeatureWorkspaceRequest,
  test_plan_repo: ITestPlanRepository = Depends(get_test_plan_repository),
) -> dict[str, Any]:
  if feature_key not in QA_FEATURE_KEYS:
    raise HTTPException(status_code=404, detail=f"Unknown QA feature: {feature_key}")
  sources = body.sources or QA_DEFAULT_SOURCES.get(feature_key, ["knowledge"])
  if not body.document_ids and not sources:
    raise HTTPException(status_code=400, detail="Upload files and/or enable live sources.")
  res = await run_grounded_feature(
    feature=feature_key,
    query=body.query,
    sources=sources,
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )
  if isinstance(res, dict) and "markdown" in res:
    await test_plan_repo.create_test_plan(
      feature_name=feature_key,
      content=res["markdown"],
      test_type=feature_key,
    )
  return res


@router.post("/features/mejoras")
@handle_grounded_errors
async def mejoras_doc(body: FeatureWorkspaceRequest) -> dict[str, Any]:
  return await run_grounded_feature(
    feature="mejoras_doc",
    query=body.query,
    sources=body.sources or ["jira", "github", "gitlab", "knowledge"],
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )


@router.post("/features/inventario")
@handle_grounded_errors
async def inventario_doc_endpoint(body: FeatureWorkspaceRequest) -> dict[str, Any]:
  return await run_grounded_feature(
    feature="inventario_doc",
    query=body.query,
    sources=body.sources or ["knowledge", "jira", "github"],
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )


@router.post("/features/levantamiento")
@handle_grounded_errors
async def levantamiento_doc_endpoint(body: FeatureWorkspaceRequest) -> dict[str, Any]:
  return await run_grounded_feature(
    feature="levantamiento_doc",
    query=body.query,
    sources=body.sources or ["knowledge", "jira", "github"],
    document_ids=body.document_ids,
    chat_context=body.chat_context,
  )


class TemplateMetadataUpdate(BaseModel):


  title: str | None = None
  module: str | None = None
  tags: list[str] | None = None
  content: str | None = None


@router.get("/templates")
async def get_templates() -> dict[str, Any]:
  return {"templates": list_templates()}


@router.get("/templates/{template_id}/content")
async def get_template_content_route(template_id: str) -> dict[str, Any]:
  detail = get_template_detail(template_id)
  if not detail:
    raise HTTPException(status_code=404, detail="Plantilla no encontrada")
  return detail


@router.post("/templates/upload")
async def upload_template(
  file: UploadFile = File(...),
  title: str = Form(default=""),
  module: str = Form(default="general"),
) -> dict[str, Any]:
  content = await file.read()
  item = save_template_file(
    filename=file.filename or "template",
    file_bytes=content,
    title=title,
    module=module,
  )
  return {"template": item}


@router.put("/templates/{template_id}")
async def edit_template(template_id: str, body: TemplateMetadataUpdate) -> dict[str, Any]:
  updated = update_template_metadata(
    template_id,
    title=body.title,
    module=body.module,
    tags=body.tags,
    content=body.content,
  )
  if not updated:
    raise HTTPException(status_code=404, detail="Plantilla no encontrada")
  return {"template": updated}


@router.delete("/templates/{template_id}")
async def remove_template(template_id: str) -> dict[str, Any]:
  success = delete_template(template_id)
  if not success:
    raise HTTPException(status_code=404, detail="Plantilla no encontrada")
  return {"ok": True, "template_id": template_id}


