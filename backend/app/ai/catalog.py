"""AI Model Catalog Service.

Publishes metadata for external API providers and client browser models directly from DB entity AIModelCatalog.
Rejects forbidden server-side local execution runtimes (GGUF, whisper-python, faster-whisper, moonshine).
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from app.models import AIModelInfo, ModelCatalogResponse

logger = logging.getLogger(__name__)

_catalog_cache: list[AIModelInfo] | None = None
_catalog_cache_ts: float = 0.0
_CACHE_TTL_SECONDS = 300
_FORBIDDEN_PROVIDERS = frozenset(["builtin", "local", "faster-whisper", "moonshine", "onnx"])

KNOWN_BROWSER_MODELS: list[dict[str, Any]] = [
    {
        "id": "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
        "raw_id": "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
        "name": "Qwen 2.5 1.5B Instruct (Equilibrado)",
        "provider": "webllm",
        "provider_name": "WebLLM (In-Browser WebGPU)",
        "description": "Gran capacidad de razonamiento en español y seguimiento de instrucciones en el navegador.",
        "context_window": "4k tokens",
        "context_length": 4096,
        "badge": "Recomendado Navegador",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Navegador WebGPU)",
        "rate_limits": "Ilimitado (Local)",
        "max_output_tokens": 2048,
        "vram_required_mb": 1200,
        "download_size": "1.2 GB",
    },
    {
        "id": "Llama-3.2-1B-Instruct-q4f16_1-MLC",
        "raw_id": "Llama-3.2-1B-Instruct-q4f16_1-MLC",
        "name": "Llama 3.2 1B Instruct (Ultra Ligero)",
        "provider": "webllm",
        "provider_name": "WebLLM (In-Browser WebGPU)",
        "description": "Excelente para máquinas con recursos reducidos y laptops ligeras sin GPU dedicada.",
        "context_window": "4k tokens",
        "context_length": 4096,
        "badge": "Ultra Ligero Navegador",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Navegador WebGPU)",
        "rate_limits": "Ilimitado (Local)",
        "max_output_tokens": 2048,
        "vram_required_mb": 880,
        "download_size": "880 MB",
    },
    {
        "id": "Llama-3.2-3B-Instruct-q4f16_1-MLC",
        "raw_id": "Llama-3.2-3B-Instruct-q4f16_1-MLC",
        "name": "Llama 3.2 3B Instruct (Alta Capacidad)",
        "provider": "webllm",
        "provider_name": "WebLLM (In-Browser WebGPU)",
        "description": "Mayor calidad sintáctica y argumentativa. Requiere WebGPU y GPU dedicada o Apple Silicon.",
        "context_window": "4k tokens",
        "context_length": 4096,
        "badge": "Alta Calidad Navegador",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Navegador WebGPU)",
        "rate_limits": "Ilimitado (Local)",
        "max_output_tokens": 2048,
        "vram_required_mb": 2200,
        "download_size": "2.2 GB",
    },
    {
        "id": "onnx-community/whisper-base",
        "raw_id": "onnx-community/whisper-base",
        "name": "Whisper Base (ONNX WebGPU)",
        "provider": "browser_asr",
        "provider_name": "Transformers.js (Browser ASR)",
        "description": "Transcripción equilibrada en español con buen balance entre velocidad y precisión.",
        "context_window": "Audio (Web Worker)",
        "context_length": 0,
        "badge": "Recomendado Voz",
        "task_type": "transcription",
        "task_label": "Transcripción de Audio",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Navegador Web Worker)",
        "rate_limits": "Ilimitado (Local)",
        "download_size": "145 MB",
        "accuracy": "Buena precisión general",
    },
    {
        "id": "onnx-community/whisper-tiny",
        "raw_id": "onnx-community/whisper-tiny",
        "name": "Whisper Tiny (ONNX WebGPU)",
        "provider": "browser_asr",
        "provider_name": "Transformers.js (Browser ASR)",
        "description": "Transcripción ultra rápida con descarga mínima para entornos de bajo ancho de banda.",
        "context_window": "Audio (Web Worker)",
        "context_length": 0,
        "badge": "Ultra Rápido Voz",
        "task_type": "transcription",
        "task_label": "Transcripción de Audio",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Navegador Web Worker)",
        "rate_limits": "Ilimitado (Local)",
        "download_size": "75 MB",
        "accuracy": "Aceptable en audio claro",
    },
    {
        "id": "onnx-community/whisper-small",
        "raw_id": "onnx-community/whisper-small",
        "name": "Whisper Small (ONNX WebGPU)",
        "provider": "browser_asr",
        "provider_name": "Transformers.js (Browser ASR)",
        "description": "Transcripción de alta fidelidad para reuniones técnicas extensas.",
        "context_window": "Audio (Web Worker)",
        "context_length": 0,
        "badge": "Alta Fidelidad Voz",
        "task_type": "transcription",
        "task_label": "Transcripción de Audio",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Navegador Web Worker)",
        "rate_limits": "Ilimitado (Local)",
        "download_size": "480 MB",
        "accuracy": "Alta fidelidad en reuniones extensas",
    },
]


def _ensure_catalog_seeded() -> None:
    try:
        from app.db.unit_of_work import SyncUnitOfWork
        with SyncUnitOfWork() as uow:
            uow.model_catalog.bulk_upsert(KNOWN_BROWSER_MODELS)
            uow.commit()
    except Exception as exc:
        logger.debug("Failed ensuring catalog seeded in DB: %s", exc)


def _load_frontier_from_db() -> list[dict[str, Any]]:
    try:
        from app.db.unit_of_work import SyncUnitOfWork
        with SyncUnitOfWork() as uow:
            items = uow.model_catalog.list()
            return items if isinstance(items, list) else []
    except Exception as exc:
        logger.debug("DB load frontier models fallback: %s", exc)
        return []


def _filter_catalog_items(items: list[dict[str, Any]]) -> list[AIModelInfo]:
    models: list[AIModelInfo] = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            continue
        provider = (item.get("provider") or "").lower()
        if provider in _FORBIDDEN_PROVIDERS or item.get("id", "").lower().endswith(".gguf"):
            continue
        try:
            models.append(AIModelInfo(**item))
        except Exception as exc:
            logger.debug("Failed to validate model %s: %s", item.get("id"), exc)
    return models


def load_local_catalog(refresh: bool = False) -> list[AIModelInfo]:
    global _catalog_cache, _catalog_cache_ts
    now = time.monotonic()
    if not refresh and _catalog_cache is not None and (now - _catalog_cache_ts) < _CACHE_TTL_SECONDS:
        return _catalog_cache

    _ensure_catalog_seeded()
    raw_items = _load_frontier_from_db()
    _catalog_cache = _filter_catalog_items(raw_items)
    _catalog_cache_ts = now
    return _catalog_cache


def has_catalog_model(model_id: str, provider: str, task_type: str) -> bool:
    """Validate a model against the persisted catalog, never a compiled allow-list."""
    p_lower = provider.lower()
    t_lower = task_type.lower()
    if t_lower == "transcription":
        alias_map = {"local": "browser_asr", "builtin": "browser_asr"}
    else:
        alias_map = {"local": "webllm", "builtin": "webllm"}
    normalized_provider = alias_map.get(p_lower, p_lower)
    return any(
        (item.id == model_id or getattr(item, "raw_id", None) == model_id)
        and item.provider.lower() == normalized_provider
        and item.task_type.lower() == t_lower
        for item in load_local_catalog()
    )


# Ordered preferences per provider and tier. Each entry is a regex searched in the model id;
# the first pattern with a match wins, and among its matches the newest version is chosen.
_TIER_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "groq": {
        "main": (r"gpt-oss-120b", r"llama-3\.3-70b", r"llama-4-maverick", r"kimi-k2"),
        "fast": (r"gpt-oss-20b", r"llama-3\.1-8b", r"llama-4-scout", r"qwen3-32b"),
    },
    "claude": {
        "main": (r"sonnet", r"opus"),
        "fast": (r"haiku",),
    },
    "openai": {
        "main": (r"^gpt-4o$", r"^gpt-4\.1$", r"^gpt-5$"),
        "fast": (r"^gpt-4o-mini$", r"^gpt-4\.1-mini$", r"^gpt-5-mini$"),
    },
    "gemini": {
        "main": (r"flash$", r"pro$"),
        "fast": (r"flash-lite$", r"flash$"),
    },
    "deepseek": {
        "main": (r"^deepseek-chat$",),
        "fast": (r"^deepseek-chat$",),
    },
    # OpenRouter ids are vendor-prefixed; the `$` anchors skip variants such as `:free` or `:extended`.
    "openrouter": {
        "main": (r"llama-3\.3-70b-instruct$",),
        "fast": (r"llama-3\.1-8b-instruct$",),
    },
}
# Variants that are never a sensible default for chat even if their name matches a pattern.
_EXCLUDED_VARIANTS = re.compile(
    r"preview|exp|audio|realtime|search|tts|transcribe|image|embedding|guard|vision|computer-use|deep-research|codex",
    re.IGNORECASE,
)
_DATE_SUFFIX = re.compile(r"\d{8}|\d{4}-\d{2}-\d{2}")


def _version_key(model_id: str) -> tuple[bool, tuple[int, ...], int]:
    """Sort key: undated aliases first, then the highest version numbers, then the shortest id."""
    dated = bool(_DATE_SUFFIX.search(model_id))
    numbers = tuple(int(n) for n in re.findall(r"\d+", _DATE_SUFFIX.sub("", model_id)))
    return (not dated, numbers, -len(model_id))


def _catalog_model_ids(provider: str, task_type: str) -> list[str]:
    p_key = (provider or "").strip().lower()
    return [
        m.raw_id or m.id
        for m in load_local_catalog()
        if m.provider.lower() == p_key and m.task_type.lower() == task_type
    ]


def catalog_chat_models(provider: str) -> list[str]:
    """Chat model ids of a provider present in the persisted catalog."""
    return _catalog_model_ids(provider, "chat_writing")


def catalog_transcription_models(provider: str) -> list[str]:
    """Transcription model ids of a cloud provider present in the persisted catalog."""
    return _catalog_model_ids(provider, "transcription")


# The catalog does not record response formats. Whisper-family models return timestamped segments
# (`verbose_json`); `gpt-*-transcribe`, realtime and live variants return text only.
_SEGMENT_MODEL = re.compile(r"whisper", re.IGNORECASE)
_TEXT_ONLY_VARIANT = re.compile(r"realtime|live|diariz", re.IGNORECASE)
# Preferred default among segment models: full large-v3 first, then turbo, then any other.
_TRANSCRIPTION_PREFERENCE = (r"large-v3$", r"large-v3-turbo", r"whisper-1$", r"whisper")


def supports_transcript_segments(model_id: str) -> bool:
    return bool(_SEGMENT_MODEL.search(model_id)) and not _TEXT_ONLY_VARIANT.search(model_id)


def segment_transcription_models(provider: str) -> list[str]:
    """Catalog transcription models of `provider` that return timestamped segments."""
    return [m for m in catalog_transcription_models(provider) if supports_transcript_segments(m)]


def pick_transcription_model(provider: str, configured: str | None = None) -> str | None:
    """`configured` when the catalog lists it with segments; otherwise the preferred catalog model.

    Returns None when the provider has no segment-capable model in the catalog.
    """
    try:
        available = segment_transcription_models(provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Catalog lookup failed while picking transcription model for %s: %s", provider, exc)
        return None
    if configured and configured in available:
        return configured
    for pattern in _TRANSCRIPTION_PREFERENCE:
        matches = [m for m in available if re.search(pattern, m, re.IGNORECASE)]
        if matches:
            return max(matches, key=_version_key)
    return None


_DIARIZATION_MODEL = re.compile(r"diariz", re.IGNORECASE)


def pick_diarization_model(provider: str, configured: str | None = None) -> tuple[str | None, bool]:
    """Diarization model for `provider` from the catalog.

    Returns `(model, catalog_known)`. `catalog_known` is False when the catalog has no transcription
    models for the provider at all (empty or unreachable), so the caller may trust `configured`.
    With a known catalog, `configured` is kept only if listed; otherwise the newest diarization
    model is returned, or None when the catalog has none.
    """
    try:
        available = catalog_transcription_models(provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Catalog lookup failed while picking diarization model for %s: %s", provider, exc)
        return None, False
    if not available:
        return None, False
    diarizers = [m for m in available if _DIARIZATION_MODEL.search(m)]
    if configured and configured in diarizers:
        return configured, True
    if not diarizers:
        return None, True
    return max(diarizers, key=_version_key), True


def pick_model(provider: str, tier: str = "main", registry_default: str | None = None) -> str | None:
    """Choose a default model for `provider` and `tier` from the persisted catalog.

    Returns the preferred match by tier pattern. When the catalog has no models at all for the
    provider (catalog unavailable or provider not synced), `registry_default` is returned as the
    last resort; when the catalog has models but none matches, returns None so the caller can fall
    back to the user's main model instead of a hardcoded name that may no longer exist.
    """
    p_key = (provider or "").strip().lower()
    try:
        available = catalog_chat_models(p_key)
    except Exception as exc:
        logger.warning("Catalog lookup failed while picking %s model for %s: %s", tier, p_key, exc)
        available = []
    if not available:
        return registry_default or None

    best = _best_for_tier(available, p_key, tier)
    if best:
        return best
    return registry_default if registry_default in available else None


def _best_for_tier(available: list[str], provider: str, tier: str) -> str | None:
    """Newest non-excluded model matching the first tier pattern that matches anything."""
    candidates = [m for m in available if not _EXCLUDED_VARIANTS.search(m)]
    for pattern in _TIER_PATTERNS.get(provider, {}).get(tier, ()):
        regex = re.compile(pattern, re.IGNORECASE)
        matches = [m for m in candidates if regex.search(m)]
        if matches:
            return max(matches, key=_version_key)
    return None


def _filter_catalog_models(models: list[AIModelInfo], provider: str, task_type: str) -> list[AIModelInfo]:
    filtered = models
    if provider and provider != "all":
        p_key = provider.lower()
        filtered = [m for m in filtered if m.provider.lower() == p_key]
    if task_type and task_type != "all":
        t_key = task_type.lower()
        filtered = [m for m in filtered if m.task_type.lower() == t_key]
    return filtered


async def get_model_catalog(refresh: bool = False, provider: str = "all", task_type: str = "all") -> ModelCatalogResponse:
    all_models = load_local_catalog(refresh=refresh)
    filtered = _filter_catalog_models(all_models, provider, task_type)

    providers_set: set[str] = set()
    for m in all_models:
        providers_set.add(m.provider)

    now_iso = datetime.now(timezone.utc).isoformat()
    err = "Error de conexión, no se pudo obtener los modelos" if not all_models else None
    return ModelCatalogResponse(
        updated_at=now_iso,
        source="ai_models_catalog_db",
        providers=sorted(list(providers_set)),
        models=filtered,
        error=err,
    )
