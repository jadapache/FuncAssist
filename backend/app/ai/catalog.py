"""AI Model Catalog Service.

Loads model metadata (rate limits, pricing, context windows, and tasks)
directly from declarative JSON catalog or PostgreSQL repository with resilient fallbacks.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from app.core.settings import ROOT_DIR, USER_DATA_DIR, WHISPER_MODELS_DIR
from app.models import AIModelInfo, ModelCatalogResponse
from app.ai.builtin_local import get_builtin_cache_dir, load_builtin_catalog, resolve_model_meta
from app.ai.builtin_seeds import DEFAULT_BUILTIN_MODELS
from app.ai.frontier_sync import KNOWN_FRONTIER_MODELS
from app.db.repositories.catalog_and_corporate_repository import AIModelCatalogRepository

logger = logging.getLogger(__name__)

CATALOG_FILE = USER_DATA_DIR / "ai" / "models_catalog.json"
FALLBACK_CATALOG_FILE = ROOT_DIR / "local" / "ai" / "models_catalog.json"

_catalog_cache: list[AIModelInfo] | None = None
_catalog_cache_ts: float = 0.0
_CACHE_TTL_SECONDS = 300
_BUILTIN_PROVIDERS = ("builtin", "local", "faster-whisper", "moonshine", "onnx")


def _resolve_context_length(tokens_str: str) -> int:
    if "131" in tokens_str:
        return 131072
    if "65" in tokens_str:
        return 65536
    if "8" in tokens_str:
        return 8192
    return 32768


def _build_builtin_chat_model(item: dict[str, Any]) -> AIModelInfo:
    model_id = item["id"]
    tokens_str = item.get("tokens", "32.768 tokens")
    return AIModelInfo(
        id=model_id,
        raw_id=item.get("filename", model_id),
        name=item.get("name", model_id),
        provider="builtin",
        provider_name="Built-in (Local)",
        description=item.get("description", ""),
        context_window=tokens_str,
        context_length=_resolve_context_length(tokens_str),
        task_type="chat_writing",
        task_label="Redacción y Chat",
        tier_type="free",
        pricing_prompt=0.0,
        pricing_completion=0.0,
        pricing_label="Gratis (Local)",
        rate_limits="Sin límite (Local)",
        badge="Built-in (Sin Ollama)",
        is_free=True,
        size=item.get("size"),
    )


def _resolve_transcription_provider_info(item: dict[str, Any], model_id: str) -> tuple[str, str, str]:
    prov = item.get("provider", "builtin")
    if prov == "onnx" or item.get("engine") == "onnxruntime" or "parakeet" in model_id or "sense-voice" in model_id:
        return ("onnx", "ONNX Runtime (Offline)", "ONNX Runtime")
    if prov == "faster-whisper" or model_id.startswith("fw-"):
        return ("faster-whisper", "Faster Whisper (CTranslate2)", "CTranslate2 Local")
    if prov == "moonshine" or model_id.startswith("moonshine"):
        return ("moonshine", "Moonshine (Useful Sensors)", "Moonshine Local")
    return ("builtin", "Whisper Local (CPU/GPU)", "Whisper Local")


def _build_builtin_transcription_model(item: dict[str, Any]) -> AIModelInfo:
    model_id = item["id"]
    prov_id, prov_name, badge = _resolve_transcription_provider_info(item, model_id)
    return AIModelInfo(
        id=model_id,
        raw_id=item.get("tag", model_id),
        name=item.get("name", model_id),
        provider=prov_id,
        provider_name=prov_name,
        description=item.get("description", ""),
        context_window="Audio local",
        context_length=0,
        task_type="transcription",
        task_label="Transcripción y Voz",
        tier_type="free",
        pricing_prompt=0.0,
        pricing_completion=0.0,
        pricing_label="Gratis (Local)",
        rate_limits="Sin límite (Local)",
        badge=badge,
        is_free=True,
        size=item.get("size"),
        accuracy=item.get("accuracy"),
    )


def _load_builtin_model_infos() -> list[AIModelInfo]:
    try:
        data = list(load_builtin_catalog(task_type=None).values())
    except Exception as exc:
        logger.debug(f"Built-in catalog file load failed: {exc}")
        data = list(DEFAULT_BUILTIN_MODELS.values())

    builtin_models: list[AIModelInfo] = []
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue
        task_type = item.get("task_type", "chat_writing")
        if task_type == "chat_writing":
            builtin_models.append(_build_builtin_chat_model(item))
        elif task_type == "transcription":
            builtin_models.append(_build_builtin_transcription_model(item))
    return builtin_models


def _load_frontier_from_db() -> list[dict[str, Any]]:
    try:
        repo = AIModelCatalogRepository()
        items = repo.list_sync()
        return items if isinstance(items, list) else []
    except Exception as exc:
        logger.debug(f"DB load frontier models fallback: {exc}")
        return []


def _load_frontier_from_file(file_path: Path) -> list[dict[str, Any]]:
    if not file_path.exists():
        return []
    try:
        parsed = json.loads(file_path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, list) else []
    except Exception as exc:
        logger.debug(f"File load failed for {file_path}: {exc}")
        return []


def _filter_non_builtin(items: list[dict[str, Any]]) -> list[AIModelInfo]:
    frontier: list[AIModelInfo] = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            continue
        if item.get("provider") in _BUILTIN_PROVIDERS:
            continue
        try:
            frontier.append(AIModelInfo(**item))
        except Exception as exc:
            logger.debug(f"Failed to validate frontier model {item.get('id')}: {exc}")
    return frontier


def load_local_catalog(refresh: bool = False) -> list[AIModelInfo]:
    global _catalog_cache, _catalog_cache_ts
    now = time.monotonic()
    if not refresh and _catalog_cache is not None and (now - _catalog_cache_ts) < _CACHE_TTL_SECONDS:
        return _catalog_cache

    raw_items = _load_frontier_from_db()
    if not raw_items:
        raw_items = _load_frontier_from_file(CATALOG_FILE)
    if not raw_items:
        raw_items = _load_frontier_from_file(FALLBACK_CATALOG_FILE)
    if not raw_items:
        raw_items = KNOWN_FRONTIER_MODELS

    frontier_models = _filter_non_builtin(raw_items)
    builtin_models = _load_builtin_model_infos()
    combined = frontier_models + builtin_models

    _catalog_cache = combined
    _catalog_cache_ts = now
    return _catalog_cache


def _get_transcription_disk_state(model: AIModelInfo, cache_dir: Path) -> tuple[bool, float]:
    clean_id = model.id.replace("whisper-", "")
    if model.provider == "onnx" or "parakeet" in model.id or "sense-voice" in model.id:
        o_dir = cache_dir / f"onnx-{model.id}"
        files = list(o_dir.glob("*.onnx")) if o_dir.exists() else []
        is_dl = len(files) > 0 and sum(f.stat().st_size for f in files) > 1024 * 1024
        return is_dl, round(sum(f.stat().st_size for f in files) / (1024 * 1024), 1) if is_dl else 0.0

    if model.provider == "faster-whisper" or model.id.startswith("fw-"):
        fw_clean = clean_id.replace("fw-", "").replace("faster-whisper-", "")
        m_bin = cache_dir / f"faster-whisper-{fw_clean}" / "model.bin"
        is_dl = m_bin.exists() and m_bin.stat().st_size > 1024 * 1024
        return is_dl, round(m_bin.stat().st_size / (1024 * 1024), 1) if is_dl else 0.0

    if model.provider == "moonshine" or model.id.startswith("moonshine"):
        m_dir = cache_dir / model.id
        is_dl = m_dir.exists() and any(m_dir.iterdir()) if m_dir.exists() else False
        return is_dl, 90.0 if ("tiny" in model.id) else (360.0 if is_dl else 0.0)

    target_pt = cache_dir / f"{clean_id}.pt"
    if not target_pt.exists():
        legacy_pt = Path.home() / ".cache" / "whisper" / f"{clean_id}.pt"
        if legacy_pt.exists():
            target_pt = legacy_pt
    is_dl = target_pt.exists() and target_pt.stat().st_size > 1024 * 1024
    return is_dl, round(target_pt.stat().st_size / (1024 * 1024), 1) if is_dl else 0.0


def _enrich_transcription_models(models: list[AIModelInfo]) -> None:
    for m in models:
        if m.task_type == "transcription" and m.provider in _BUILTIN_PROVIDERS:
            try:
                is_dl, size_mb = _get_transcription_disk_state(m, WHISPER_MODELS_DIR)
                m.is_downloaded = is_dl
                m.disk_size_mb = size_mb
            except Exception as exc:
                logger.debug(f"Transcription state check failed for {m.id}: {exc}")


def _enrich_chat_models(models: list[AIModelInfo]) -> None:
    cache_dir = get_builtin_cache_dir()
    for m in models:
        if m.provider == "builtin" and m.task_type == "chat_writing":
            try:
                meta = resolve_model_meta(m.id)
                if meta:
                    gguf = cache_dir / meta["filename"]
                    is_dl = gguf.exists() and gguf.stat().st_size > 10 * 1024 * 1024
                    m.is_downloaded = is_dl
                    m.disk_size_mb = round(gguf.stat().st_size / (1024 * 1024), 1) if is_dl else 0.0
            except Exception as exc:
                logger.debug(f"Chat model state check failed for {m.id}: {exc}")


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
    try:
        models = load_local_catalog(refresh=refresh)
    except Exception as exc:
        logger.error(f"Catalog loading raised exception: {exc}")
        models = []

    source = "local_json"
    error_msg = None
    if not models:
        error_msg = "Error de conexión, no se pudo obtener los modelos"
        source = "error"

    _enrich_transcription_models(models)
    _enrich_chat_models(models)

    filtered_models = _filter_catalog_models(models, provider, task_type)
    all_providers = sorted(list(set(m.provider for m in filtered_models))) if filtered_models else []

    return ModelCatalogResponse(
        updated_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        providers=all_providers,
        models=filtered_models,
        error=error_msg,
    )
