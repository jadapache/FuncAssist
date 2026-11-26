import os
from typing import Any, Literal, Optional
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.catalog import catalog_chat_models, get_model_catalog, has_catalog_model
from app.ai.endpoint_security import validate_remote_endpoint_url
from app.ai.frontier_sync import get_frontier_sync_status, sync_frontier_models_catalog
from app.ai.providers.factory import clear_provider_cache, get_ai_settings
from app.ai.providers.registry import find_provider_spec
from app.api.deps import get_current_user
from app.api.middleware.error_handlers import handle_grounded_errors
from app.core.storage import save_user_ai_settings

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
    openrouter_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    transcription_groq_api_key: Optional[str] = None
    transcription_openai_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    fallback_models: Optional[list[str]] = None
    fast_model: Optional[str] = None
    transcription_vocabulary: Optional[str] = Field(default=None, max_length=1000)
    transcription_fillers: Optional[list[str]] = Field(default=None, max_length=100)
    transcription_cleanup: Optional[Literal["off", "rules", "llm"]] = None
    transcription_diarization: Optional[Literal["auto", "off"]] = None
    transcription_browser_diarization: Optional[Literal["on", "off"]] = None


def _validate_tier_models_against_catalog(data: dict[str, Any], current: dict[str, Any]) -> None:
    """Reject a fast model or fallback models that are not in the provider's synced catalog.

    Values come from the payload or, when only the provider changes, from the stored settings; stored
    values that do not exist for the new provider are cleared instead of rejected, since the user did
    not send them. Providers without catalog entries (e.g. remote Ollama) are not validated.
    """
    provider = (data.get("provider") or current.get("provider") or "").lower()
    spec = find_provider_spec(provider)
    if not spec:
        return
    try:
        available = set(catalog_chat_models(spec.id))
    except Exception:
        available = set()
    if not available:
        return
    provider_changed = "provider" in data and find_provider_spec(current.get("provider") or "") is not spec

    if data.get("fast_model"):
        if data["fast_model"] not in available:
            raise HTTPException(
                status_code=400,
                detail=f"El modelo rápido '{data['fast_model']}' no existe en el catálogo de {spec.name}.",
            )
    elif provider_changed and current.get("fast_model") and current["fast_model"] not in available:
        data["fast_model"] = ""

    if "fallback_models" in data:
        unknown = [m for m in data["fallback_models"] if m not in available]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Modelos de respaldo no disponibles en el catálogo de {spec.name}: {', '.join(unknown)}.",
            )
    elif provider_changed and current.get("fallback_models"):
        data["fallback_models"] = [m for m in current["fallback_models"] if m in available]


@router.get("/models/catalog")
@handle_grounded_errors
async def ai_models_catalog(
    refresh: bool = False,
    provider: str = "all",
    task_type: str = "all",
) -> dict[str, Any]:
    sync_error = None
    if refresh:
        sync_res = await sync_frontier_models_catalog(force_remote=True)
        if sync_res.get("status") == "error":
            sync_error = "No se ha podido refrescar el catálogo de proveedores desde LiteLLM."

    catalog = await get_model_catalog(refresh=refresh, provider=provider, task_type=task_type)
    dumped = catalog.model_dump()
    if sync_error:
        dumped["error"] = sync_error
    return dumped


@router.post("/models/sync")
@handle_grounded_errors
async def sync_ai_models_catalog(
    force_remote: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually trigger background synchronization of frontier models from LiteLLM."""
    sync_result = await sync_frontier_models_catalog(force_remote=force_remote)
    catalog = await get_model_catalog(refresh=True)
    return {
        "sync": sync_result,
        "catalog": catalog.model_dump(),
    }


@router.get("/models/sync-status")
@handle_grounded_errors
async def get_ai_models_sync_status(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve last frontier models synchronization status."""
    return get_frontier_sync_status()


@router.get("/settings")
@handle_grounded_errors
async def get_settings_endpoint(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    config = get_ai_settings(user_id=user_id)
    provider = (config.get("provider") or "").lower()
    spec = find_provider_spec(provider)
    active_key_set = False
    if spec:
        if spec.id == "ollama_remote" or "ollama" in spec.aliases:
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
        "openrouter_api_key_set": bool(config.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY")),
        "deepseek_api_key_set": bool(config.get("deepseek_api_key") or os.getenv("DEEPSEEK_API_KEY")),
        "transcription_groq_api_key_set": bool(
            config.get("transcription_groq_api_key") or config.get("groq_api_key") or os.getenv("GROQ_API_KEY")
        ),
        "transcription_openai_api_key_set": bool(
            config.get("transcription_openai_api_key") or config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        ),
        "ollama_base_url": config.get("ollama_base_url"),
        "fallback_models": config.get("fallback_models") or [],
        "fast_model": config.get("fast_model") or None,
        "transcription_vocabulary": config.get("transcription_vocabulary") or "",
        "transcription_fillers": config.get("transcription_fillers") or [],
        "transcription_cleanup": config.get("transcription_cleanup") or "rules",
        "transcription_diarization": config.get("transcription_diarization") or "auto",
        "transcription_browser_diarization": config.get("transcription_browser_diarization") or "off",
        "active_api_key_set": active_key_set,
        "user_id": user_id,
    }


@router.put("/settings")
@handle_grounded_errors
async def update_ai_settings(
    body: AISettingsUpdate = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    data = body.model_dump(exclude_none=True)

    if "inference_provider" in data and "provider" not in data:
        data["provider"] = data.pop("inference_provider")
    elif "inference_provider" in data:
        data.pop("inference_provider")

    if "inference_model" in data and "model" not in data:
        data["model"] = data.pop("inference_model")
    elif "inference_model" in data:
        data.pop("inference_model")

    model_candidate = data.get("model") or ""
    if model_candidate.lower().endswith(".gguf"):
        raise HTTPException(
            status_code=400,
            detail="Los modelos en formato GGUF no están admitidos. Usa WebLLM en navegador o una API externa.",
        )

    if "fallback_models" in data:
        fallbacks = [str(m).strip() for m in data["fallback_models"] if str(m).strip()]
        if any(m.lower().endswith(".gguf") for m in fallbacks):
            raise HTTPException(status_code=400, detail="Los modelos de respaldo no pueden ser GGUF.")
        if len(fallbacks) > 3:
            raise HTTPException(status_code=400, detail="Se admiten como máximo 3 modelos de respaldo.")
        data["fallback_models"] = list(dict.fromkeys(fallbacks))
    if (data.get("fast_model") or "").lower().endswith(".gguf"):
        raise HTTPException(status_code=400, detail="El modelo rápido no puede ser GGUF.")
    if "fast_model" in data:
        data["fast_model"] = str(data["fast_model"]).strip()
    if "transcription_fillers" in data:
        fillers = [str(f).strip().lower() for f in data["transcription_fillers"] if str(f).strip()]
        if any(len(f) > 40 for f in fillers):
            raise HTTPException(status_code=400, detail="Cada muletilla admite como máximo 40 caracteres.")
        data["transcription_fillers"] = list(dict.fromkeys(fillers))
    if "transcription_vocabulary" in data:
        data["transcription_vocabulary"] = str(data["transcription_vocabulary"]).strip()

    _validate_tier_models_against_catalog(data, get_ai_settings(user_id=user_id))

    prov = (data.get("provider") or "").lower()
    if prov in {"ollama", "ollama_remote"}:
        base_url = (data.get("ollama_base_url") or "").strip()
        if base_url:
            ok, err = validate_remote_endpoint_url(base_url)
            if not ok:
                raise HTTPException(status_code=400, detail=err)

    if prov in {"local", "builtin", "webllm"} and model_candidate:
        if not has_catalog_model(model_candidate, prov, "chat_writing"):
            raise HTTPException(status_code=400, detail="El modelo WebLLM no existe en el catálogo persistido.")

    trans_provider = (data.get("transcription_provider") or "").lower()
    trans_model = data.get("transcription_model") or ""
    if trans_provider in {"local", "builtin", "browser_asr"} and trans_model:
        if not has_catalog_model(trans_model, trans_provider, "transcription"):
            raise HTTPException(status_code=400, detail="El modelo ASR no existe en el catálogo persistido.")

    save_user_ai_settings(user_id, data)
    clear_provider_cache(user_id)
    return await get_settings_endpoint(current_user=current_user)
