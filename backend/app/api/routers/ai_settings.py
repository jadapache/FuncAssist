import os
from typing import Any, Optional
from fastapi import APIRouter, Body
from pydantic import BaseModel

from app.ai.catalog import get_model_catalog
from app.ai.providers.factory import get_ai_settings
from app.ai.providers.registry import find_provider_spec
from app.api.middleware.error_handlers import handle_grounded_errors
from app.core.storage import load_app_settings, save_app_settings

router = APIRouter(prefix="/ai", tags=["ai-settings"])


class AISettingsUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    inference_provider: Optional[str] = None
    inference_model: Optional[str] = None
    transcription_provider: Optional[str] = None
    transcription_model: Optional[str] = None
    voice_command_provider: Optional[str] = None
    voice_command_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    transcription_groq_api_key: Optional[str] = None
    transcription_openai_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None


@router.get("/models/catalog")
@handle_grounded_errors
async def ai_models_catalog(
    refresh: bool = False,
    provider: str = "all",
    task_type: str = "all",
) -> dict[str, Any]:
    catalog = await get_model_catalog(refresh=refresh, provider=provider, task_type=task_type)
    return catalog.model_dump()


@router.get("/settings")
@handle_grounded_errors
async def get_settings_endpoint() -> dict[str, Any]:
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


@router.put("/settings")
@handle_grounded_errors
async def update_ai_settings(body: AISettingsUpdate = Body(...)) -> dict[str, Any]:
    current = load_app_settings()
    ai = dict(current.get("ai") or {})
    data = body.model_dump(exclude_none=True)

    # Normalize inference_provider -> provider
    if "inference_provider" in data and "provider" not in data:
        data["provider"] = data.pop("inference_provider")
    elif "inference_provider" in data:
        data.pop("inference_provider")

    # Normalize inference_model -> model
    if "inference_model" in data and "model" not in data:
        data["model"] = data.pop("inference_model")
    elif "inference_model" in data:
        data.pop("inference_model")

    for key, value in data.items():
        ai[key] = value
    save_app_settings({"ai": ai})
    return await get_settings_endpoint()
