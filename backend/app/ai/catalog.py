"""AI Model Catalog Service.

Publishes metadata for external API providers and client browser models directly from DB entity AIModelCatalog.
Rejects forbidden server-side local execution runtimes (GGUF, whisper-python, faster-whisper, moonshine).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from app.models import AIModelInfo, ModelCatalogResponse
from app.db.repositories.catalog_and_corporate_repository import AIModelCatalogRepository

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
        repo = AIModelCatalogRepository()
        repo.bulk_upsert_sync(KNOWN_BROWSER_MODELS)
    except Exception as exc:
        logger.debug("Failed ensuring catalog seeded in DB: %s", exc)


def _load_frontier_from_db() -> list[dict[str, Any]]:
    try:
        repo = AIModelCatalogRepository()
        items = repo.list_sync()
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


def _filter_catalog_models(models: list[AIModelInfo], provider: str, task_type: str) -> list[AIModelInfo]:
    filtered = models
    if provider and provider != "all":
        p_key = provider.lower()
        filtered = [m for m in filtered if m.provider.lower() == p_key]
    if task_type and task_type != "all":
        t_key = task_type.lower()
        filtered = [m for m in filtered if m.task_type.lower() == t_key]
    return filtered


async def get_model_catalog(
    refresh: bool = False,
    provider: str = "all",
    task_type: str = "all",
) -> ModelCatalogResponse:
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
