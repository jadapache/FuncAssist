from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.request

logger = logging.getLogger(__name__)

# Cache directory for standalone built-in GGUF models (without Ollama)
def get_builtin_cache_dir() -> Path:
    cache_dir = Path(os.path.expanduser("~")) / ".cache" / "qa_mgmt" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# Catalog of built-in models with verified Hugging Face direct download URLs
BUILTIN_LLM_CATALOG: Dict[str, Dict[str, Any]] = {
    "qwen2.5:1.5b": {
        "id": "qwen2.5:1.5b",
        "name": "Qwen 2.5 1.5B (Ultra Ligero)",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size": "~1.0 GiB",
        "tokens": "32k tokens",
        "description": "Modelo ultra rápido y liviano para análisis ágil en cualquier CPU o laptop sin GPU dedicada.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "aliases": ["qwen:1.5b", "qwen1.5b"],
    },
    "qwen2.5:3b": {
        "id": "qwen2.5:3b",
        "name": "Qwen 2.5 3B (Equilibrado / Recomendado)",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "size": "~1.9 GiB",
        "tokens": "32k tokens",
        "description": "Modelo insignia equilibrado de alta fidelidad para redacción de historias de usuario y análisis QA.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "aliases": ["qwen3.5:2b", "qwen:3b", "qwen3b"],
    },
    "llama3.2:1b": {
        "id": "llama3.2:1b",
        "name": "Llama 3.2 1B (Meta Instantáneo)",
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "size": "~770 MiB",
        "tokens": "128k tokens",
        "description": "Modelo ligero de Meta de última generación, bajo consumo de memoria y respuesta instantánea.",
        "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "aliases": ["llama:1b", "llama1b"],
    },
    "llama3.2:3b": {
        "id": "llama3.2:3b",
        "name": "Llama 3.2 3B (Alta Calidad)",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size": "~2.0 GiB",
        "tokens": "128k tokens",
        "description": "Alta precisión en razonamiento, casos de prueba y análisis estructurado en español e inglés.",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "aliases": ["llama:3b", "llama3b"],
    },
    "deepseek-r1:1.5b": {
        "id": "deepseek-r1:1.5b",
        "name": "DeepSeek R1 1.5B (Razonamiento)",
        "filename": "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "size": "~1.0 GiB",
        "tokens": "64k tokens",
        "description": "Modelo de razonamiento estructurado (Chain-of-Thought) para lógica de validación QA profunda.",
        "url": "https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "aliases": ["deepseek-r1:8b", "deepseek:1.5b"],
    },
    "gemma-2-2b": {
        "id": "gemma-2-2b",
        "name": "Gemma 2 2B (Google Open Model)",
        "filename": "gemma-2-2b-it-Q4_K_M.gguf",
        "size": "~1.6 GiB",
        "tokens": "8k tokens",
        "description": "Modelo de Google optimizado para seguimiento de instrucciones y redacción técnica concisa.",
        "url": "https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf",
        "aliases": ["gemma3:1b", "gemma:2b"],
    },
}


def resolve_model_meta(model_id: str) -> Optional[Dict[str, Any]]:
    """Resolves model metadata by id or alias."""
    clean = model_id.strip().lower()
    if clean in BUILTIN_LLM_CATALOG:
        return BUILTIN_LLM_CATALOG[clean]
    for meta in BUILTIN_LLM_CATALOG.values():
        if clean in meta.get("aliases", []):
            return meta
        if clean == meta.get("filename", "").lower():
            return meta
    return None


def get_builtin_models_info() -> List[Dict[str, Any]]:
    """Inspects the local cache directory to list all built-in LLM models and their download status."""
    cache_dir = get_builtin_cache_dir()
    results: List[Dict[str, Any]] = []

    for model_id, meta in BUILTIN_LLM_CATALOG.items():
        filename = meta["filename"]
        target_file = cache_dir / filename
        is_downloaded = target_file.exists() and target_file.stat().st_size > 10 * 1024 * 1024  # > 10MB
        disk_size_mb = round(target_file.stat().st_size / (1024 * 1024), 1) if is_downloaded else 0.0

        results.append({
            "id": model_id,
            "name": meta["name"],
            "filename": filename,
            "size": meta["size"],
            "tokens": meta["tokens"],
            "description": meta["description"],
            "is_downloaded": is_downloaded,
            "disk_size_mb": disk_size_mb,
            "file_path": str(target_file) if is_downloaded else None,
        })

    return results


def download_builtin_model_file(
    model_id: str,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> Path:
    """Downloads a built-in GGUF model file directly from Hugging Face into the cache directory."""
    meta = resolve_model_meta(model_id)
    if not meta:
        raise ValueError(
            f"Modelo built-in desconocido: '{model_id}'. "
            f"Modelos disponibles: {list(BUILTIN_LLM_CATALOG.keys())}"
        )

    url = meta["url"]
    filename = meta["filename"]
    cache_dir = get_builtin_cache_dir()
    target_file = cache_dir / filename
    tmp_file = cache_dir / f"{filename}.download"

    # If target already exists and is non-empty (>10MB), skip
    if target_file.exists() and target_file.stat().st_size > 10 * 1024 * 1024:
        logger.info(f"Built-in model '{model_id}' already exists at {target_file}")
        return target_file

    logger.info(f"Downloading built-in model '{model_id}' from {url} to {target_file}")

    # Use browser-like User-Agent to avoid HF blocks
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; QA-Project-MGMT/1.0; +https://github.com)"},
    )

    with urllib.request.urlopen(req) as response:
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB chunks for speed

        with open(tmp_file, "wb") as f_out:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and progress_callback:
                    pct = round((downloaded / total_size) * 100, 1)
                    progress_callback(downloaded, total_size, pct)

    # Atomically replace target
    if target_file.exists():
        target_file.unlink()
    tmp_file.rename(target_file)
    logger.info(f"Built-in model '{model_id}' downloaded successfully to {target_file}")
    return target_file


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
