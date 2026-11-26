"""Frontier AI Models Catalog Sync Service.

Fetches and synchronizes frontier model specifications (pricing, context windows,
and output token limits) from LiteLLM's model pricing database in the background.
Operates safely offline using LiteLLM bundled cost map when remote connectivity is unavailable.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

# Ensure LiteLLM uses offline cost map on startup and doesn't block or spam warnings
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import httpx
import litellm

# Configure litellm quiet mode
litellm.telemetry = False
litellm.suppress_debug_info = True
litellm.set_verbose = False

from app.models.ai import AIModelInfo

logger = logging.getLogger(__name__)

LITELLM_REMOTE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

# State tracking for background sync
_last_sync_result: dict[str, Any] = {
    "last_sync": None,
    "source": "none",
    "status": "idle",
    "models_count": 0,
    "error": None,
}

PROVIDER_META: dict[str, dict[str, Any]] = {
    "groq": {"name": "Groq Cloud", "badge_default": "Groq LPU", "is_free_default": True},
    "claude": {"name": "Anthropic Claude", "badge_default": "Anthropic", "is_free_default": False},
    "openai": {"name": "OpenAI", "badge_default": "OpenAI", "is_free_default": False},
    "gemini": {"name": "Google Gemini", "badge_default": "Google DeepMind", "is_free_default": False},
    "deepseek": {"name": "DeepSeek", "badge_default": "DeepSeek", "is_free_default": False},
    "openrouter": {"name": "OpenRouter", "badge_default": "OpenRouter", "is_free_default": False},
}


async def fetch_litellm_cost_map(timeout_seconds: float = 6.0) -> tuple[dict[str, Any], str]:
    """Fetch latest LiteLLM model cost map asynchronously from remote repository."""
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        resp = await client.get(LITELLM_REMOTE_URL)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and len(data) > 100:
                try:
                    litellm.model_cost.update(data)
                except Exception:
                    pass
                return data, "remote_litellm"
        raise RuntimeError(f"Respuesta no válida de LiteLLM (status {resp.status_code})")


def _format_context_window(ctx_len: int) -> str:
    """Format integer context tokens to human readable string."""
    if ctx_len >= 1_000_000:
        return f"{ctx_len // 1_000_000}M tokens" if ctx_len % 1_000_000 == 0 else f"{ctx_len / 1_000_000:.1f}M tokens"
    if ctx_len >= 1000:
        return f"{ctx_len // 1000}k tokens"
    return f"{ctx_len} tokens"


_EXTRA_KEY_PREFIXES = {
    "claude": ("anthropic",),
    "gemini": ("gemini", "google"),
    "openai": ("openai",),
    "groq": ("groq",),
}


def _find_litellm_entry(cost_map: dict[str, Any], model_id: str, provider: str) -> dict[str, Any] | None:
    """Lookup model in LiteLLM cost map with various provider key variations."""
    clean_id = model_id.strip()
    bare_id = clean_id.split("/")[-1]
    extra_names = (clean_id, bare_id) if provider == "claude" else (clean_id,)
    candidates = [clean_id, f"{provider}/{clean_id}", bare_id]
    candidates += [f"{prefix}/{name}" for prefix in _EXTRA_KEY_PREFIXES.get(provider, ()) for name in extra_names]

    exact = next((cost_map[c] for c in candidates if isinstance(cost_map.get(c), dict)), None)
    if exact is not None:
        return exact
    # Flexible matching
    return next(
        (v for k, v in cost_map.items() if isinstance(v, dict) and (k == clean_id or k.endswith(f"/{clean_id}"))),
        None,
    )


def _capabilities(entry: dict[str, Any]) -> list[str]:
    """Spanish labels of the capabilities a LiteLLM entry declares."""
    sees_images = entry.get("supports_vision") or "image" in (entry.get("supported_modalities") or [])
    declared = (
        ("razonamiento", entry.get("supports_reasoning")),
        ("visión multimodal", sees_images),
        ("herramientas", entry.get("supports_function_calling")),
        ("prompt caching", entry.get("supports_prompt_caching")),
    )
    return [label for label, supported in declared if supported]


def _build_model_description(
    entry: dict[str, Any] | None,
    provider_name: str,
    model_id: str,
    task_type: str,
    context_window: str,
) -> str:
    """Generate dynamic model description based on LiteLLM capabilities."""
    if task_type == "transcription":
        diarize = " con diarización" if "diarize" in model_id.lower() else ""
        return f"Modelo de audio para transcripción{diarize} alojado en {provider_name}."

    caps = _capabilities(entry or {})
    cap_str = f", optimizado para {', '.join(caps)}" if caps else ""
    return f"Modelo {provider_name} con ventana de {context_window}{cap_str}."


_PROVIDER_BY_LITELLM_PREFIX = {
    "groq": "groq",
    "openai": "openai",
    "anthropic": "claude",
    "claude": "claude",
    "gemini": "gemini",
    "google": "gemini",
    "openrouter": "openrouter",
    "deepseek": "deepseek",
}
_TASK_BY_LITELLM_MODE = {"audio_transcription": "transcription", "chat": "chat_writing"}


def _provider_and_model_id(raw_key: str, entry: dict[str, Any]) -> tuple[str | None, str]:
    """Provider id and model id of a cost-map key, which may or may not carry a provider prefix."""
    prefix, separator, model_name = raw_key.partition("/")
    if separator and model_name:
        return _PROVIDER_BY_LITELLM_PREFIX.get(prefix.lower()), model_name.strip()
    if not separator:
        raw_provider = (entry.get("litellm_provider") or "").strip().lower()
        return _PROVIDER_BY_LITELLM_PREFIX.get(raw_provider), raw_key.strip()
    return None, ""


def _catalog_candidate(provider: str, model_id: str, task_type: str) -> dict[str, Any]:
    """Catalog entry for a model found in LiteLLM, before it is enriched with its specs."""
    meta = PROVIDER_META.get(provider, {})
    transcription = task_type == "transcription"
    return {
        "id": model_id,
        "raw_id": model_id,
        "name": model_id,
        "provider": provider,
        "provider_name": meta.get("name", provider.title()),
        "description": f"Modelo {provider.title()} descubierto desde LiteLLM.",
        "context_window": "Audio (hasta 25MB)" if transcription else "128k tokens",
        "context_length": 0 if transcription else 131072,
        "badge": meta.get("badge_default", provider.title()),
        "task_type": task_type,
        "task_label": "Transcripción y Voz" if transcription else "Redacción y Chat",
        "is_free": bool(meta.get("is_free_default", False)),
        "tier_type": "free" if provider == "groq" else "paid",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "",
        "rate_limits": "Standard Provider Limits",
    }


def _discover_litellm_models(cost_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build catalog candidates directly from LiteLLM model keys.

    LiteLLM is the discovery source; the curated list only supplies optional
    presentation metadata for models that are already present in this result.
    """
    discovered: dict[str, dict[str, Any]] = {}
    for raw_key, entry in cost_map.items():
        if not isinstance(raw_key, str) or not isinstance(entry, dict):
            continue
        task_type = _TASK_BY_LITELLM_MODE.get((entry.get("mode") or "").strip().lower())
        provider, model_id = _provider_and_model_id(raw_key, entry)
        if task_type and provider and model_id:
            discovered[f"{provider}:{model_id}"] = _catalog_candidate(provider, model_id, task_type)
    return discovered


def _positive_number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and value > 0 else None


def _apply_litellm_specs(item: dict[str, Any], entry: dict[str, Any]) -> None:
    """Context window, output limit and per-million-token prices from a LiteLLM entry."""
    max_input = _positive_number(entry.get("max_input_tokens") or entry.get("max_tokens"))
    if max_input:
        item["context_length"] = int(max_input)
        if item["task_type"] == "chat_writing":
            item["context_window"] = _format_context_window(int(max_input))

    max_output = _positive_number(entry.get("max_output_tokens") or entry.get("max_tokens"))
    if max_output:
        item["max_output_tokens"] = int(max_output)

    for field, cost_key in (("pricing_prompt", "input_cost_per_token"), ("pricing_completion", "output_cost_per_token")):
        cost = entry.get(cost_key)
        if isinstance(cost, (int, float)):
            item[field] = round(float(cost) * 1_000_000, 4)


def _apply_pricing_label(item: dict[str, Any]) -> None:
    """Pricing label plus the free/paid flags it implies."""
    prompt_price = item["pricing_prompt"]
    completion_price = item["pricing_completion"]
    if item["provider"] == "groq":
        item.update(tier_type="free", is_free=True, pricing_prompt=0.0, pricing_completion=0.0)
        provider_name = PROVIDER_META.get("groq", {}).get("name", "Groq")
        item["pricing_label"] = f"$0.00 (Gratuito en {provider_name})"
    elif item["task_type"] == "transcription":
        if prompt_price <= 0:
            item["pricing_label"] = "$0.00 (Gratuito en Groq Cloud)"
        elif prompt_price < 0.1:
            item["pricing_label"] = f"${prompt_price:.3f} por minuto de audio"
        else:
            item["pricing_label"] = f"${prompt_price:.2f} / 1M tokens"
    elif prompt_price == 0.0 and completion_price == 0.0:
        item.update(tier_type="free", is_free=True, pricing_label="$0.00 (Gratuito)")
    else:
        item.update(
            tier_type="paid",
            is_free=False,
            pricing_label=f"${prompt_price:.2f} / 1M input • ${completion_price:.2f} / 1M output",
        )


def _enrich_model(item: dict[str, Any], cost_map: dict[str, Any]) -> None:
    """Complete a discovered model with the specs, description and price label LiteLLM supports."""
    entry = _find_litellm_entry(cost_map, item["id"], item["provider"])
    if entry:
        _apply_litellm_specs(item, entry)
    item["description"] = _build_model_description(
        entry, item["provider_name"], item["id"], item["task_type"], item["context_window"]
    )
    _apply_pricing_label(item)


def _validated_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The models that satisfy AIModelInfo, as plain dicts; invalid ones are logged and skipped."""
    validated: list[dict[str, Any]] = []
    for item in models:
        try:
            validated.append(AIModelInfo(**item).model_dump())
        except Exception as e:
            logger.warning(f"Skipping model {item.get('id')} due to validation error: {e}")
    return validated


def _persist_external_models(models: list[dict[str, Any]]) -> None:
    """Replace the external catalog in the database; a failure is logged, not raised."""
    try:
        from app.db.unit_of_work import SyncUnitOfWork

        with SyncUnitOfWork() as uow:
            uow.model_catalog.replace_external(models)
            uow.commit()
    except Exception as db_err:
        logger.warning(f"Failed to persist frontier models catalog into DB: {db_err}")


def _invalidate_catalog_cache() -> None:
    try:
        from app.ai import catalog as cat_mod

        cat_mod._catalog_cache = None
        cat_mod._catalog_cache_ts = 0.0
    except Exception:
        pass


def _record_sync(last_sync: str, source: str, status: str, models_count: int, error: str | None) -> dict[str, Any]:
    global _last_sync_result
    _last_sync_result = {
        "last_sync": last_sync,
        "source": source,
        "status": status,
        "models_count": models_count,
        "error": error,
    }
    return _last_sync_result


async def sync_frontier_models_catalog(force_remote: bool = False) -> dict[str, Any]:
    """Synchronize frontier model catalog with the latest LiteLLM database.

    Enriches context windows, max tokens, and pricing for all frontier models.
    Persists the updated external catalog in AIModelCatalog, preserving browser seeds.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cost_map, source = await fetch_litellm_cost_map(timeout_seconds=8.0 if force_remote else 5.0)

        # External models are discovered exclusively from LiteLLM. Browser models are owned
        # by catalog.py and preserved by replace_external().
        discovered = _discover_litellm_models(cost_map)
        for item in discovered.values():
            _enrich_model(item, cost_map)

        validated = _validated_models(list(discovered.values()))
        _persist_external_models(validated)
        _invalidate_catalog_cache()

        logger.info(f"Frontier models catalog synced successfully ({len(validated)} models from {source})")
        return _record_sync(now_iso, source, "success", len(validated), None)
    except Exception as exc:
        logger.warning(f"Failed to sync frontier models catalog: {exc}")
        return _record_sync(now_iso, "error", "error", 0, str(exc))


def get_frontier_sync_status() -> dict[str, Any]:
    """Return the last synchronization status."""
    return dict(_last_sync_result)
