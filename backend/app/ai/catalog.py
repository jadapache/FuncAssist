"""AI Model Catalog Service.

Loads model metadata (rate limits, pricing, context windows, and tasks)
directly from declarative JSON catalog (models_catalog.json).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import LOCAL_DIR
from app.models import AIModelInfo, ModelCatalogResponse

logger = logging.getLogger(__name__)

CATALOG_FILE = LOCAL_DIR / "ai" / "models_catalog.json"

_catalog_cache: list[AIModelInfo] | None = None
_catalog_cache_ts: float = 0.0
_CACHE_TTL_SECONDS = 300  # 5 minutos


def load_local_catalog(refresh: bool = False) -> list[AIModelInfo]:
    """Load verified model list from local/ai/models_catalog.json file."""
    global _catalog_cache, _catalog_cache_ts

    now = time.monotonic()
    if not refresh and _catalog_cache is not None and (now - _catalog_cache_ts) < _CACHE_TTL_SECONDS:
        return _catalog_cache

    if not CATALOG_FILE.exists():
        logger.error(f"Catalog file not found at {CATALOG_FILE}")
        return []

    try:
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _catalog_cache = [AIModelInfo(**item) for item in data]
        _catalog_cache_ts = now
        return _catalog_cache
    except Exception as e:
        logger.error(f"Failed to load AI models catalog from {CATALOG_FILE}: {e}")
        return []


async def get_model_catalog(
    refresh: bool = False,
    provider: str = "all",
    task_type: str = "all",
) -> ModelCatalogResponse:
    """Retrieve catalog of AI models from the declarative JSON registry."""
    models = load_local_catalog(refresh=refresh)

    source = "local_json"
    error_msg = None

    if not models:
        error_msg = "Error de conexión, no se pudo obtener los modelos"
        source = "error"

    # Dynamically enrich builtin Whisper models with local download state
    whisper_cache = Path.home() / ".cache" / "whisper"
    for m in models:
        if m.provider == "builtin" and m.task_type == "transcription":
            clean_id = m.id.replace("whisper-", "")
            target_pt = whisper_cache / f"{clean_id}.pt"
            is_dl = target_pt.exists() and target_pt.stat().st_size > 1024 * 1024
            m.is_downloaded = is_dl
            m.disk_size_mb = round(target_pt.stat().st_size / (1024 * 1024), 1) if is_dl else 0.0

    # Dynamically enrich builtin chat_writing LLM models with local download state
    from app.ai.builtin_local import get_builtin_cache_dir, resolve_model_meta
    builtin_cache = get_builtin_cache_dir()
    for m in models:
        if m.provider == "builtin" and m.task_type == "chat_writing":
            meta = resolve_model_meta(m.id)
            if meta:
                target_gguf = builtin_cache / meta["filename"]
                is_dl = target_gguf.exists() and target_gguf.stat().st_size > 10 * 1024 * 1024
                m.is_downloaded = is_dl
                m.disk_size_mb = round(target_gguf.stat().st_size / (1024 * 1024), 1) if is_dl else 0.0

    # Filter by provider
    if provider and provider != "all":
        prov_key = provider.lower()
        models = [m for m in models if m.provider.lower() == prov_key]

    # Filter by task_type (chat_writing vs transcription)
    if task_type and task_type != "all":
        task_key = task_type.lower()
        models = [m for m in models if m.task_type.lower() == task_key]

    all_providers = sorted(list(set(m.provider for m in models))) if models else []

    return ModelCatalogResponse(
        updated_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        providers=all_providers,
        models=models,
        error=error_msg,
    )

