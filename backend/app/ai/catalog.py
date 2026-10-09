"""AI Model Catalog Service.

Loads model metadata (rate limits, pricing, context windows, and tasks)
directly from declarative JSON catalog (models_catalog.json).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import shutil

# Ensure LiteLLM offline cost map default
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from app.core.settings import ROOT_DIR, USER_DATA_DIR
from app.models import AIModelInfo, ModelCatalogResponse

logger = logging.getLogger(__name__)

CATALOG_FILE = USER_DATA_DIR / "ai" / "models_catalog.json"
FALLBACK_CATALOG_FILE = ROOT_DIR / "local" / "ai" / "models_catalog.json"
BUILTIN_CATALOG_FILE = USER_DATA_DIR / "ai" / "builtin_models_catalog.json"
FALLBACK_BUILTIN_CATALOG_FILE = ROOT_DIR / "local" / "ai" / "builtin_models_catalog.json"

_catalog_cache: list[AIModelInfo] | None = None
_catalog_cache_ts: float = 0.0
_CACHE_TTL_SECONDS = 300  # 5 minutos


def _load_builtin_model_infos() -> list[AIModelInfo]:
    """Load built-in models from builtin_models_catalog.json and map them to AIModelInfo."""
    target_file = BUILTIN_CATALOG_FILE
    if not target_file.exists():
        if FALLBACK_BUILTIN_CATALOG_FILE.exists():
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(FALLBACK_BUILTIN_CATALOG_FILE, target_file)
            except Exception:
                target_file = FALLBACK_BUILTIN_CATALOG_FILE
        else:
            return []
    elif FALLBACK_BUILTIN_CATALOG_FILE.exists():
        try:
            fb_data = json.loads(FALLBACK_BUILTIN_CATALOG_FILE.read_text(encoding="utf-8"))
            usr_data = json.loads(target_file.read_text(encoding="utf-8"))
            usr_ids = {item["id"] for item in usr_data if isinstance(item, dict) and "id" in item}
            missing = [item for item in fb_data if isinstance(item, dict) and item.get("id") not in usr_ids]
            if missing:
                usr_data.extend(missing)
                target_file.write_text(json.dumps(usr_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.debug(f"Built-in catalog sync check skipped: {exc}")

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load built-in catalog from {target_file}: {e}")
        return []

    builtin_models: list[AIModelInfo] = []
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue
        task_type = item.get("task_type", "chat_writing")
        model_id = item["id"]
        name = item.get("name", model_id)
        description = item.get("description", "")
        size = item.get("size")

        if task_type == "chat_writing":
            tokens_str = item.get("tokens", "32.768 tokens")
            ctx_len = 32768
            if "131" in tokens_str:
                ctx_len = 131072
            elif "65" in tokens_str:
                ctx_len = 65536
            elif "8" in tokens_str:
                ctx_len = 8192

            builtin_models.append(
                AIModelInfo(
                    id=model_id,
                    raw_id=item.get("filename", model_id),
                    name=name,
                    provider="builtin",
                    provider_name="Built-in (Local)",
                    description=description,
                    context_window=tokens_str,
                    context_length=ctx_len,
                    task_type="chat_writing",
                    task_label="Redacción y Chat",
                    tier_type="free",
                    pricing_prompt=0.0,
                    pricing_completion=0.0,
                    pricing_label="Gratis (Local)",
                    rate_limits="Sin límite (Local)",
                    badge="Built-in (Sin Ollama)",
                    is_free=True,
                    size=size,
                )
            )
        elif task_type == "transcription":
            prov = item.get("provider", "builtin")
            if prov == "onnx" or item.get("engine") == "onnxruntime" or "parakeet" in model_id or "sense-voice" in model_id:
                prov_id = "onnx"
                prov_name = "ONNX Runtime (Offline)"
                badge = "ONNX Runtime"
            elif prov == "faster-whisper" or model_id.startswith("fw-"):
                prov_id = "faster-whisper"
                prov_name = "Faster Whisper (CTranslate2)"
                badge = "CTranslate2 Local"
            elif prov == "moonshine" or model_id.startswith("moonshine"):
                prov_id = "moonshine"
                prov_name = "Moonshine (Useful Sensors)"
                badge = "Moonshine Local"
            else:
                prov_id = "builtin"
                prov_name = "Whisper Local (CPU/GPU)"
                badge = "Whisper Local"

            builtin_models.append(
                AIModelInfo(
                    id=model_id,
                    raw_id=item.get("tag", model_id),
                    name=name,
                    provider=prov_id,
                    provider_name=prov_name,
                    description=description,
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
                    size=size,
                    accuracy=item.get("accuracy"),
                )
            )

    return builtin_models


def load_local_catalog(refresh: bool = False) -> list[AIModelInfo]:
    """Load verified model list combining frontier models (models_catalog.json) and built-in models (builtin_models_catalog.json)."""
    global _catalog_cache, _catalog_cache_ts

    now = time.monotonic()
    if not refresh and _catalog_cache is not None and (now - _catalog_cache_ts) < _CACHE_TTL_SECONDS:
        return _catalog_cache

    target_file = CATALOG_FILE
    if not target_file.exists():
        if FALLBACK_CATALOG_FILE.exists():
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(FALLBACK_CATALOG_FILE, target_file)
            except Exception:
                target_file = FALLBACK_CATALOG_FILE
        else:
            logger.error(f"Catalog file not found at {CATALOG_FILE}")
            target_file = None
    elif FALLBACK_CATALOG_FILE.exists():
        # Ensure user catalog has any new frontier models added to repo template
        try:
            fb_data = json.loads(FALLBACK_CATALOG_FILE.read_text(encoding="utf-8"))
            usr_data = json.loads(target_file.read_text(encoding="utf-8"))
            usr_ids = {item["id"] for item in usr_data if isinstance(item, dict) and "id" in item}
            missing = [item for item in fb_data if isinstance(item, dict) and item.get("id") not in usr_ids]
            if missing:
                usr_data.extend(missing)
                target_file.write_text(json.dumps(usr_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.debug(f"Catalog sync check skipped: {exc}")

    frontier_models: list[AIModelInfo] = []
    if target_file and target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            frontier_models = [
                AIModelInfo(**item) for item in data
                if isinstance(item, dict) and item.get("provider") not in ("builtin", "local", "faster-whisper", "moonshine", "onnx")
            ]
        except Exception as e:
            logger.error(f"Failed to load AI models catalog from {target_file}: {e}")

    builtin_models = _load_builtin_model_infos()
    combined = frontier_models + builtin_models

    _catalog_cache = combined
    _catalog_cache_ts = now
    return _catalog_cache


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

    # Dynamically enrich builtin Whisper and local transcription models with download state
    from app.core.settings import WHISPER_MODELS_DIR
    whisper_cache = WHISPER_MODELS_DIR
    for m in models:
        if m.task_type == "transcription" and m.provider in ("builtin", "local", "faster-whisper", "moonshine", "onnx"):
            clean_id = m.id.replace("whisper-", "")
            if m.provider == "onnx" or "parakeet" in m.id or "sense-voice" in m.id:
                o_dir = whisper_cache / f"onnx-{m.id}"
                onnx_files = list(o_dir.glob("*.onnx")) if o_dir.exists() else []
                is_dl = len(onnx_files) > 0 and sum(f.stat().st_size for f in onnx_files) > 1024 * 1024
                m.is_downloaded = is_dl
                m.disk_size_mb = round(sum(f.stat().st_size for f in onnx_files) / (1024 * 1024), 1) if is_dl else 0.0
            elif m.provider == "faster-whisper" or m.id.startswith("fw-"):
                clean_fw = clean_id.replace("fw-", "").replace("faster-whisper-", "")
                fw_dir = whisper_cache / f"faster-whisper-{clean_fw}"
                model_bin = fw_dir / "model.bin"
                is_dl = model_bin.exists() and model_bin.stat().st_size > 1024 * 1024
                m.is_downloaded = is_dl
                m.disk_size_mb = round(model_bin.stat().st_size / (1024 * 1024), 1) if is_dl else 0.0
            elif m.provider == "moonshine" or m.id.startswith("moonshine"):
                m_dir = whisper_cache / m.id
                is_dl = m_dir.exists() and any(m_dir.iterdir()) if m_dir.exists() else False
                m.is_downloaded = is_dl
                m.disk_size_mb = 90.0 if ("tiny" in m.id) else (360.0 if is_dl else 0.0)
            else:
                target_pt = whisper_cache / f"{clean_id}.pt"
                if not target_pt.exists():
                    legacy_pt = Path.home() / ".cache" / "whisper" / f"{clean_id}.pt"
                    if legacy_pt.exists():
                        target_pt = legacy_pt
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

