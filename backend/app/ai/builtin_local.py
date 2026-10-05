from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.request

from app.core.settings import LOCAL_DIR

logger = logging.getLogger(__name__)

# Dedicated local JSON catalog path for built-in models
BUILTIN_CATALOG_FILE = LOCAL_DIR / "ai" / "builtin_models_catalog.json"

# Cache directory for standalone built-in GGUF models (without Ollama)
def get_builtin_cache_dir() -> Path:
    cache_dir = Path(os.path.expanduser("~")) / ".cache" / "qa_mgmt" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def load_builtin_catalog(task_type: Optional[str] = "chat_writing") -> Dict[str, Dict[str, Any]]:
    """Loads built-in models directly from local/ai/builtin_models_catalog.json file."""
    if not BUILTIN_CATALOG_FILE.exists():
        logger.warning(f"Built-in catalog file not found at {BUILTIN_CATALOG_FILE}")
        return {}

    try:
        with open(BUILTIN_CATALOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                result = {}
                for item in data:
                    if not isinstance(item, dict) or "id" not in item:
                        continue
                    if task_type is None or item.get("task_type") == task_type:
                        result[item["id"]] = item
                return result
    except Exception as e:
        logger.error(f"Error reading {BUILTIN_CATALOG_FILE}: {e}")

    return {}



# Dynamic catalog dictionary
BUILTIN_LLM_CATALOG: Dict[str, Dict[str, Any]] = load_builtin_catalog()


# --- Download Task Tracking & Cancellation State ---
_ACTIVE_DOWNLOADS: Dict[str, Dict[str, Any]] = {}
_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_DOWNLOAD_LOCK = threading.Lock()


def get_active_downloads_status() -> List[Dict[str, Any]]:
    """Returns status of all ongoing built-in model downloads."""
    with _DOWNLOAD_LOCK:
        return list(_ACTIVE_DOWNLOADS.values())


def cancel_builtin_model_download(model_id: str) -> bool:
    """Signals cancellation to an active download."""
    clean_id = model_id.strip()
    with _DOWNLOAD_LOCK:
        event = _CANCEL_EVENTS.get(clean_id)
        if event:
            event.set()
            if clean_id in _ACTIVE_DOWNLOADS:
                _ACTIVE_DOWNLOADS[clean_id]["status"] = "cancelled"
                _ACTIVE_DOWNLOADS[clean_id]["stageText"] = "Cancelando descarga..."
            logger.info(f"Cancellation requested for built-in model download: {clean_id}")
            return True
        # Check by filename / alias if necessary
        meta = resolve_model_meta(model_id)
        if meta and meta.get("id") in _CANCEL_EVENTS:
            _CANCEL_EVENTS[meta["id"]].set()
            return True
    return False


def resolve_model_meta(model_id: str) -> Optional[Dict[str, Any]]:
    """Resolves model metadata by id or alias from the loaded local catalog."""
    catalog = load_builtin_catalog()
    clean = model_id.strip().lower()
    if clean in catalog:
        return catalog[clean]
    for meta in catalog.values():
        if clean in [a.lower() for a in meta.get("aliases", [])]:
            return meta
        if clean == meta.get("filename", "").lower():
            return meta
    return None


def get_builtin_models_info() -> List[Dict[str, Any]]:
    """Inspects the local cache directory to list all built-in LLM models from local JSON catalog and their download status."""
    catalog = load_builtin_catalog()
    cache_dir = get_builtin_cache_dir()
    results: List[Dict[str, Any]] = []

    for model_id, meta in catalog.items():
        filename = meta["filename"]
        target_file = cache_dir / filename
        is_downloaded = target_file.exists() and target_file.stat().st_size > 10 * 1024 * 1024  # > 10MB
        disk_size_mb = round(target_file.stat().st_size / (1024 * 1024), 1) if is_downloaded else 0.0

        results.append({
            "id": model_id,
            "name": meta["name"],
            "filename": filename,
            "size": meta["size"],
            "tokens": meta.get("tokens", ""),
            "description": meta.get("description", ""),
            "is_downloaded": is_downloaded,
            "disk_size_mb": disk_size_mb,
            "file_path": str(target_file) if is_downloaded else None,
        })

    return results


def download_builtin_model_file(
    model_id: str,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> Path:
    """Downloads a built-in GGUF model file directly from Hugging Face into the cache directory with cancellation support."""
    meta = resolve_model_meta(model_id)
    catalog = load_builtin_catalog()
    if not meta:
        raise ValueError(
            f"Modelo built-in desconocido: '{model_id}'. "
            f"Modelos disponibles en catálogo local: {list(catalog.keys())}"
        )

    canonical_id = meta["id"]
    url = meta["url"]
    filename = meta["filename"]
    cache_dir = get_builtin_cache_dir()
    target_file = cache_dir / filename
    tmp_file = cache_dir / f"{filename}.download"

    # If target already exists and is non-empty (>10MB), skip
    if target_file.exists() and target_file.stat().st_size > 10 * 1024 * 1024:
        logger.info(f"Built-in model '{model_id}' already exists at {target_file}")
        return target_file

    cancel_event = threading.Event()
    start_time = time.time()
    last_update_time = 0.0

    with _DOWNLOAD_LOCK:
        _CANCEL_EVENTS[canonical_id] = cancel_event
        _ACTIVE_DOWNLOADS[canonical_id] = {
            "id": canonical_id,
            "title": f"Descargando {meta['name']}",
            "filename": filename,
            "progress": 0,
            "status": "downloading",
            "stageText": "Iniciando descarga...",
            "speedOrSize": "0 MB",
            "eta": None,
        }

    logger.info(f"Downloading built-in model '{canonical_id}' from {url} to {target_file}")

    # Use browser-like User-Agent to avoid HF blocks
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; QA-Project-MGMT/1.0; +https://github.com)"},
    )

    try:
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1 MB chunks for high throughput

            with open(tmp_file, "wb") as f_out:
                while True:
                    if cancel_event.is_set():
                        logger.warning(f"Download cancelled by user for model {canonical_id}")
                        raise RuntimeError(f"Descarga de '{meta['name']}' cancelada por el usuario.")

                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_update_time >= 0.4:
                        last_update_time = now
                        elapsed = max(0.1, now - start_time)
                        speed_mb = (downloaded / (1024 * 1024)) / elapsed
                        speed_str = f"{speed_mb:.1f} MB/s"

                        pct = round((downloaded / total_size) * 100, 1) if total_size > 0 else 0.0
                        dl_mb = round(downloaded / (1024 * 1024), 1)
                        tot_mb = round(total_size / (1024 * 1024), 1) if total_size > 0 else 0.0

                        eta_str = None
                        if speed_mb > 0 and total_size > downloaded:
                            eta_sec = int((total_size - downloaded) / (speed_mb * 1024 * 1024))
                            eta_str = f"{eta_sec // 60}m {eta_sec % 60}s" if eta_sec >= 60 else f"{eta_sec}s"

                        with _DOWNLOAD_LOCK:
                            if canonical_id in _ACTIVE_DOWNLOADS:
                                _ACTIVE_DOWNLOADS[canonical_id].update({
                                    "progress": int(pct),
                                    "stageText": f"{dl_mb} MB de {tot_mb} MB ({speed_str})",
                                    "speedOrSize": f"{dl_mb}/{tot_mb} MB",
                                    "eta": eta_str,
                                })

                        if progress_callback:
                            progress_callback(downloaded, total_size, pct)

        # Atomically replace target
        if target_file.exists():
            target_file.unlink()
        tmp_file.rename(target_file)

        with _DOWNLOAD_LOCK:
            if canonical_id in _ACTIVE_DOWNLOADS:
                _ACTIVE_DOWNLOADS[canonical_id].update({
                    "progress": 100,
                    "status": "complete",
                    "stageText": "Descarga completada con éxito",
                    "speedOrSize": "Listo",
                    "eta": None,
                })

        logger.info(f"Built-in model '{canonical_id}' downloaded successfully to {target_file}")
        return target_file

    except Exception as exc:
        # Clean up temporary download file if aborted or errored
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except Exception:
                pass

        with _DOWNLOAD_LOCK:
            if canonical_id in _ACTIVE_DOWNLOADS:
                is_cancel = cancel_event.is_set() or "cancelada" in str(exc).lower()
                _ACTIVE_DOWNLOADS[canonical_id].update({
                    "status": "cancelled" if is_cancel else "failed",
                    "stageText": "Descarga cancelada" if is_cancel else f"Error: {exc}",
                })
        raise
    finally:
        with _DOWNLOAD_LOCK:
            _CANCEL_EVENTS.pop(canonical_id, None)


def delete_builtin_model_file(model_id: str) -> bool:
    """Deletes a downloaded built-in model from disk."""
    meta = resolve_model_meta(model_id)
    cache_dir = get_builtin_cache_dir()

    filename = meta["filename"] if meta else model_id
    if not filename.endswith(".gguf"):
        filename = f"{filename}.gguf"

    target_file = cache_dir / filename
    tmp_file = cache_dir / f"{filename}.download"

    deleted = False
    if target_file.exists():
        try:
            target_file.unlink()
            deleted = True
            logger.info(f"Deleted built-in model file: {target_file}")
        except Exception as exc:
            logger.error(f"Error deleting built-in model file {target_file}: {exc}")
            raise

    if tmp_file.exists():
        try:
            tmp_file.unlink()
        except Exception:
            pass

    return deleted
