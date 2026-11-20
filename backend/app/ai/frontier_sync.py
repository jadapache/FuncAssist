"""Frontier AI Models Catalog Sync Service.

Fetches and synchronizes frontier model specifications (pricing, context windows,
and output token limits) from LiteLLM's model pricing database in the background.
Operates safely offline using LiteLLM bundled cost map when remote connectivity is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
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
                    if hasattr(litellm, "model_cost") and isinstance(litellm.model_cost, dict):
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


def _find_litellm_entry(cost_map: dict[str, Any], model_id: str, provider: str) -> dict[str, Any] | None:
    """Lookup model in LiteLLM cost map with various provider key variations."""
    clean_id = model_id.strip()
    candidates = [
        clean_id,
        f"{provider}/{clean_id}",
        clean_id.split("/")[-1],
    ]
    if provider == "claude":
        candidates.extend([f"anthropic/{clean_id}", f"anthropic/{clean_id.split('/')[-1]}"])
    elif provider == "gemini":
        candidates.extend([f"gemini/{clean_id}", f"google/{clean_id}"])
    elif provider == "openai":
        candidates.extend([f"openai/{clean_id}"])
    elif provider == "groq":
        candidates.extend([f"groq/{clean_id}"])

    for cand in candidates:
        if cand in cost_map and isinstance(cost_map[cand], dict):
            return cost_map[cand]

    # Flexible matching
    for k, v in cost_map.items():
        if isinstance(v, dict):
            if k == clean_id or k.endswith(f"/{clean_id}"):
                return v

    return None


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

    entry_data = entry or {}
    caps: list[str] = []
    if entry_data.get("supports_reasoning"):
        caps.append("razonamiento")
    if entry_data.get("supports_vision") or "image" in (entry_data.get("supported_modalities") or []):
        caps.append("visión multimodal")
    if entry_data.get("supports_function_calling"):
        caps.append("herramientas")
    if entry_data.get("supports_prompt_caching"):
        caps.append("prompt caching")

    cap_str = f", optimizado para {', '.join(caps)}" if caps else ""
    return f"Modelo {provider_name} con ventana de {context_window}{cap_str}."


def _discover_litellm_models(cost_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build catalog candidates directly from LiteLLM model keys.

    LiteLLM is the discovery source; the curated list only supplies optional
    presentation metadata for models that are already present in this result.
    """
    provider_prefixes = {
        "groq": "groq",
        "openai": "openai",
        "anthropic": "claude",
        "claude": "claude",
        "gemini": "gemini",
        "google": "gemini",
        "openrouter": "openrouter",
        "deepseek": "deepseek",
    }
    discovered: dict[str, dict[str, Any]] = {}
    for raw_key, entry in cost_map.items():
        if not isinstance(raw_key, str) or not isinstance(entry, dict):
            continue

        mode = (entry.get("mode") or "").strip().lower()
        if mode == "audio_transcription":
            task_type = "transcription"
        elif mode == "chat":
            task_type = "chat_writing"
        else:
            continue

        prefix, separator, model_name = raw_key.partition("/")
        if separator and model_name:
            provider = provider_prefixes.get(prefix.lower())
            model_id = model_name.strip()
        elif not separator:
            raw_prov = (entry.get("litellm_provider") or "").strip().lower()
            provider = provider_prefixes.get(raw_prov)
            model_id = raw_key.strip()
        else:
            continue

        if not provider or not model_id:
            continue

        key = f"{provider}:{model_id}"
        discovered[key] = {
            "id": model_id,
            "raw_id": model_id,
            "name": model_id,
            "provider": provider,
            "provider_name": PROVIDER_META.get(provider, {}).get("name", provider.title()),
            "description": f"Modelo {provider.title()} descubierto desde LiteLLM.",
            "context_window": "Audio (hasta 25MB)" if task_type == "transcription" else "128k tokens",
            "context_length": 0 if task_type == "transcription" else 131072,
            "badge": PROVIDER_META.get(provider, {}).get("badge_default", provider.title()),
            "task_type": task_type,
            "task_label": "Transcripción y Voz" if task_type == "transcription" else "Redacción y Chat",
            "is_free": bool(PROVIDER_META.get(provider, {}).get("is_free_default", False)),
            "tier_type": "free" if provider == "groq" else "paid",
            "pricing_prompt": 0.0,
            "pricing_completion": 0.0,
            "pricing_label": "",
            "rate_limits": "Standard Provider Limits",
        }
    return discovered


async def sync_frontier_models_catalog(force_remote: bool = False) -> dict[str, Any]:
    """Synchronize frontier model catalog with the latest LiteLLM database.
    
    Enriches context windows, max tokens, and pricing for all frontier models.
    Persists the updated external catalog in AIModelCatalog, preserving browser seeds.
    """
    global _last_sync_result
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cost_map, source = await fetch_litellm_cost_map(timeout_seconds=8.0 if force_remote else 5.0)

        # External models are discovered exclusively from LiteLLM. Browser models are owned
        # by catalog.py and preserved by replace_external().
        model_dict = _discover_litellm_models(cost_map)

        # Enrich each frontier model with LiteLLM specs
        for _, model_item in model_dict.items():
            mid = model_item["id"]
            prov = model_item.get("provider", "groq")
            task_type = model_item.get("task_type", "chat_writing")
            prov_info = PROVIDER_META.get(prov, {})
            model_item.setdefault("provider_name", prov_info.get("name", prov.title()))
            model_item.setdefault("task_label", "Transcripción y Voz" if task_type == "transcription" else "Redacción y Chat")
            model_item.setdefault("rate_limits", "Standard Provider Limits")

            entry = _find_litellm_entry(cost_map, mid, prov)
            if entry:
                max_inp = entry.get("max_input_tokens") or entry.get("max_tokens")
                if max_inp and isinstance(max_inp, (int, float)) and max_inp > 0:
                    model_item["context_length"] = int(max_inp)
                    if task_type == "chat_writing":
                        model_item["context_window"] = _format_context_window(int(max_inp))

                max_out = entry.get("max_output_tokens") or entry.get("max_tokens")
                if max_out and isinstance(max_out, (int, float)) and max_out > 0:
                    if "max_output_tokens" not in model_item or model_item["max_output_tokens"] is None:
                        model_item["max_output_tokens"] = int(max_out)

                inp_cost = entry.get("input_cost_per_token")
                out_cost = entry.get("output_cost_per_token")

                if inp_cost is not None and isinstance(inp_cost, (int, float)):
                    cost_1m_prompt = round(float(inp_cost) * 1_000_000, 4)
                    model_item["pricing_prompt"] = cost_1m_prompt

                if out_cost is not None and isinstance(out_cost, (int, float)):
                    cost_1m_comp = round(float(out_cost) * 1_000_000, 4)
                    model_item["pricing_completion"] = cost_1m_comp

            # Ensure all required AIModelInfo fields are present with valid defaults
            model_item.setdefault("context_length", 131072 if task_type == "chat_writing" else 0)
            model_item.setdefault("context_window", _format_context_window(model_item["context_length"]) if task_type == "chat_writing" else "Audio (hasta 25MB)")
            model_item.setdefault("pricing_prompt", 0.0)
            model_item.setdefault("pricing_completion", 0.0)
            model_item.setdefault("is_free", prov == "groq")
            model_item.setdefault("tier_type", "free" if model_item["is_free"] else "paid")

            prompt_p = model_item.get("pricing_prompt", 0.0)
            comp_p = model_item.get("pricing_completion", 0.0)

            model_item["description"] = _build_model_description(
                entry,
                model_item["provider_name"],
                mid,
                task_type,
                model_item["context_window"],
            )

            if prov == "groq" and model_item.get("is_free", True):
                model_item["tier_type"] = "free"
                model_item["is_free"] = True
                model_item["pricing_prompt"] = 0.0
                model_item["pricing_completion"] = 0.0
                model_item["pricing_label"] = f"$0.00 (Gratuito en {prov_info.get('name', 'Groq')})"
            elif task_type == "transcription":
                if prompt_p > 0:
                    model_item["pricing_label"] = f"${prompt_p:.3f} por minuto de audio" if prompt_p < 0.1 else f"${prompt_p:.2f} / 1M tokens"
                else:
                    model_item["pricing_label"] = "$0.00 (Gratuito en Groq Cloud)"
            elif not model_item.get("pricing_label"):
                if prompt_p == 0.0 and comp_p == 0.0:
                    model_item["tier_type"] = "free"
                    model_item["is_free"] = True
                    model_item["pricing_label"] = "$0.00 (Gratuito)"
                else:
                    model_item["tier_type"] = "paid"
                    model_item["is_free"] = False
                    model_item["pricing_label"] = f"${prompt_p:.2f} / 1M input • ${comp_p:.2f} / 1M output"

        # Validate with AIModelInfo
        validated_list: list[dict[str, Any]] = []
        for item in model_dict.values():
            try:
                validated_model = AIModelInfo(**item)
                validated_list.append(validated_model.model_dump())
            except Exception as e:
                logger.warning(f"Skipping model {item.get('id')} due to validation error: {e}")

        # Persist directly to PostgreSQL database entity
        try:
            from app.db.unit_of_work import SyncUnitOfWork
            with SyncUnitOfWork() as uow:
                uow.model_catalog.replace_external(validated_list)
                uow.commit()
        except Exception as db_err:
            logger.warning(f"Failed to persist frontier models catalog into DB: {db_err}")

        # Invalidate catalog memory cache in catalog module
        try:
            from app.ai import catalog as cat_mod
            cat_mod._catalog_cache = None
            cat_mod._catalog_cache_ts = 0.0
        except Exception:
            pass

        _last_sync_result = {
            "last_sync": now_iso,
            "source": source,
            "status": "success",
            "models_count": len(validated_list),
            "error": None,
        }
        logger.info(f"Frontier models catalog synced successfully ({len(validated_list)} models from {source})")
        return _last_sync_result

    except Exception as exc:
        err_msg = f"Failed to sync frontier models catalog: {exc}"
        logger.warning(err_msg)
        _last_sync_result = {
            "last_sync": now_iso,
            "source": "error",
            "status": "error",
            "models_count": 0,
            "error": str(exc),
        }
        return _last_sync_result


def get_frontier_sync_status() -> dict[str, Any]:
    """Return the last synchronization status."""
    return dict(_last_sync_result)
