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


def _catalog_models_for(spec: Any) -> set[str]:
    """Chat models of the provider's synced catalog; empty when it is unavailable."""
    try:
        return set(catalog_chat_models(spec.id))
    except Exception:
        return set()


def _check_fast_model(data: dict[str, Any], current: dict[str, Any], available: set[str], spec: Any, changed: bool) -> None:
    if data.get("fast_model"):
        if data["fast_model"] not in available:
            raise HTTPException(
                status_code=400,
                detail=f"El modelo rápido '{data['fast_model']}' no existe en el catálogo de {spec.name}.",
            )
    elif changed and current.get("fast_model") and current["fast_model"] not in available:
        data["fast_model"] = ""


def _check_fallback_models(
    data: dict[str, Any], current: dict[str, Any], available: set[str], spec: Any, changed: bool
) -> None:
    if "fallback_models" in data:
        unknown = [m for m in data["fallback_models"] if m not in available]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Modelos de respaldo no disponibles en el catálogo de {spec.name}: {', '.join(unknown)}.",
            )
    elif changed and current.get("fallback_models"):
        data["fallback_models"] = [m for m in current["fallback_models"] if m in available]


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
    available = _catalog_models_for(spec)
    if not available:
        return
    provider_changed = "provider" in data and find_provider_spec(current.get("provider") or "") is not spec
    _check_fast_model(data, current, available, spec, provider_changed)
    _check_fallback_models(data, current, available, spec, provider_changed)


@router.get("/models/catalog")
@handle_grounded_errors
async def ai_models_catalog(refresh: bool = False, provider: str = "all", task_type: str = "all") -> dict[str, Any]:
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
async def sync_ai_models_catalog(force_remote: bool = True, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
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


_MAX_FALLBACK_MODELS = 3
_MAX_FILLER_CHARS = 40

# Reported as-is, or None when empty.
_OPTIONAL_SETTINGS = (
    "provider",
    "model",
    "transcription_provider",
    "transcription_model",
    "voice_command_provider",
    "voice_command_model",
    "fast_model",
)
# Reported with the default shown when nothing is stored.
_SETTING_DEFAULTS: dict[str, Any] = {
    "fallback_models": [],
    "transcription_vocabulary": "",
    "transcription_fillers": [],
    "transcription_cleanup": "rules",
    "transcription_diarization": "auto",
    "transcription_browser_diarization": "off",
}
# Flag name, stored keys that count, environment variable that counts.
_KEY_FLAGS = (
    ("openai_api_key_set", ("openai_api_key",), "OPENAI_API_KEY"),
    ("claude_api_key_set", ("claude_api_key",), "ANTHROPIC_API_KEY"),
    ("groq_api_key_set", ("groq_api_key",), "GROQ_API_KEY"),
    ("gemini_api_key_set", ("gemini_api_key",), "GEMINI_API_KEY"),
    ("openrouter_api_key_set", ("openrouter_api_key",), "OPENROUTER_API_KEY"),
    ("deepseek_api_key_set", ("deepseek_api_key",), "DEEPSEEK_API_KEY"),
    ("transcription_groq_api_key_set", ("transcription_groq_api_key", "groq_api_key"), "GROQ_API_KEY"),
    ("transcription_openai_api_key_set", ("transcription_openai_api_key", "openai_api_key"), "OPENAI_API_KEY"),
)


def _active_key_set(config: dict[str, Any]) -> bool:
    """Whether the selected provider has what it needs to be called (key, env var or base URL)."""
    spec = find_provider_spec((config.get("provider") or "").lower())
    if not spec:
        return False
    if spec.id == "ollama_remote" or "ollama" in spec.aliases:
        return bool(config.get("ollama_base_url"))
    if spec.config_key:
        return bool(config.get(spec.config_key) or (spec.env_key and os.getenv(spec.env_key)))
    return bool(spec.env_key and os.getenv(spec.env_key))


@router.get("/settings")
@handle_grounded_errors
async def get_settings_endpoint(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    config = get_ai_settings(user_id=user_id)
    return {
        **{name: config.get(name) or None for name in _OPTIONAL_SETTINGS},
        **{name: config.get(name) or default for name, default in _SETTING_DEFAULTS.items()},
        **{
            flag: bool(any(config.get(key) for key in keys) or os.getenv(env_var))
            for flag, keys, env_var in _KEY_FLAGS
        },
        "ollama_base_url": config.get("ollama_base_url"),
        "active_api_key_set": _active_key_set(config),
        "user_id": user_id,
    }


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _apply_inference_aliases(data: dict[str, Any]) -> None:
    """`inference_*` fields are older names of `provider`/`model`; the new name wins when both come."""
    for alias, target in (("inference_provider", "provider"), ("inference_model", "model")):
        if alias in data:
            data.setdefault(target, data.pop(alias))


def _normalize_fallback_models(data: dict[str, Any]) -> None:
    if "fallback_models" not in data:
        return
    fallbacks = [str(m).strip() for m in data["fallback_models"] if str(m).strip()]
    if any(m.lower().endswith(".gguf") for m in fallbacks):
        raise _reject("Los modelos de respaldo no pueden ser GGUF.")
    if len(fallbacks) > _MAX_FALLBACK_MODELS:
        raise _reject(f"Se admiten como máximo {_MAX_FALLBACK_MODELS} modelos de respaldo.")
    data["fallback_models"] = list(dict.fromkeys(fallbacks))


def _normalize_fast_model(data: dict[str, Any]) -> None:
    if (data.get("fast_model") or "").lower().endswith(".gguf"):
        raise _reject("El modelo rápido no puede ser GGUF.")
    if "fast_model" in data:
        data["fast_model"] = str(data["fast_model"]).strip()


def _normalize_transcription_settings(data: dict[str, Any]) -> None:
    if "transcription_fillers" in data:
        fillers = [str(f).strip().lower() for f in data["transcription_fillers"] if str(f).strip()]
        if any(len(f) > _MAX_FILLER_CHARS for f in fillers):
            raise _reject(f"Cada muletilla admite como máximo {_MAX_FILLER_CHARS} caracteres.")
        data["transcription_fillers"] = list(dict.fromkeys(fillers))
    if "transcription_vocabulary" in data:
        data["transcription_vocabulary"] = str(data["transcription_vocabulary"]).strip()


def _validate_ollama_endpoint(data: dict[str, Any]) -> None:
    if (data.get("provider") or "").lower() not in {"ollama", "ollama_remote"}:
        return
    base_url = (data.get("ollama_base_url") or "").strip()
    if base_url:
        ok, err = validate_remote_endpoint_url(base_url)
        if not ok:
            raise _reject(err)


def _require_catalog_model(
    data: dict[str, Any], provider_key: str, model_key: str, providers: set[str], task_type: str, error: str
) -> None:
    """An in-browser model, when one is chosen, must exist in the persisted catalog."""
    provider = (data.get(provider_key) or "").lower()
    model = data.get(model_key) or ""
    if provider in providers and model and not has_catalog_model(model, provider, task_type):
        raise _reject(error)


def _validate_browser_models(data: dict[str, Any]) -> None:
    """In-browser (WebLLM / ASR) models must exist in the persisted catalog."""
    _require_catalog_model(
        data, "provider", "model", {"local", "builtin", "webllm"}, "chat_writing",
        "El modelo WebLLM no existe en el catálogo persistido.",
    )
    _require_catalog_model(
        data, "transcription_provider", "transcription_model", {"local", "builtin", "browser_asr"},
        "transcription", "El modelo ASR no existe en el catálogo persistido.",
    )


@router.put("/settings")
@handle_grounded_errors
async def update_ai_settings(
    body: AISettingsUpdate = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    data = body.model_dump(exclude_none=True)
    _apply_inference_aliases(data)

    if (data.get("model") or "").lower().endswith(".gguf"):
        raise _reject("Los modelos en formato GGUF no están admitidos. Usa WebLLM en navegador o una API externa.")
    _normalize_fallback_models(data)
    _normalize_fast_model(data)
    _normalize_transcription_settings(data)

    _validate_tier_models_against_catalog(data, get_ai_settings(user_id=user_id))
    _validate_ollama_endpoint(data)
    _validate_browser_models(data)

    save_user_ai_settings(user_id, data)
    clear_provider_cache(user_id)
    return await get_settings_endpoint(current_user=current_user)
