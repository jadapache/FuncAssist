"""Frontier AI Models Catalog Sync Service.

Fetches and synchronizes frontier model specifications (pricing, context windows,
and output token limits) from LiteLLM's model pricing database in the background.
Operates safely offline using LiteLLM bundled cost map when remote connectivity is unavailable.
"""

from __future__ import annotations

import asyncio
import json
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

from app.core.settings import ROOT_DIR, USER_DATA_DIR
from app.models.ai import AIModelInfo

logger = logging.getLogger(__name__)

CATALOG_FILE = USER_DATA_DIR / "ai" / "models_catalog.json"
FALLBACK_CATALOG_FILE = ROOT_DIR / "local" / "ai" / "models_catalog.json"
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

KNOWN_FRONTIER_MODELS: list[dict[str, Any]] = [
    # Groq models
    {
        "id": "llama-3.3-70b-versatile",
        "raw_id": "llama-3.3-70b-versatile",
        "name": "Llama 3.3 70B Versatile (Recomendado)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Modelo insignia de Meta de código abierto optimizado en LPU para análisis profundo, historias de usuario y requerimientos QA.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "Recomendado (Free Tier)",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 1,000 RPD • 6k TPM",
        "max_output_tokens": 4096,
    },
    {
        "id": "llama-3.1-8b-instant",
        "raw_id": "llama-3.1-8b-instant",
        "name": "Llama 3.1 8B Instant (Ultra Rápido)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Modelo ultra veloz de baja latencia ideal para resúmenes ágiles y clasificaciones rápidas.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "Ultra Rápido (Free Tier)",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 14,400 RPD • 20k TPM",
        "max_output_tokens": 4096,
    },
    {
        "id": "qwen/qwen3.8-27b",
        "raw_id": "qwen/qwen3.8-27b",
        "name": "Qwen 3.8 27B (Razonamiento & Chat)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Modelo Qwen 3.8 de Alibaba alojado en Groq, alta precisión en español y lógica estructurada.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "Qwen Oficial (Groq)",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 1,000 OTPM • 8k TPM (Salida máx: 950)",
        "max_output_tokens": 950,
    },
    {
        "id": "openai/gpt-oss-120b",
        "raw_id": "openai/gpt-oss-120b",
        "name": "GPT OSS 120B (OpenAI en Groq)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Modelo abierto de alta escala de OpenAI alojado en la infraestructura acelerada de Groq.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "GPT OSS (Groq)",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 1,000 RPD • 8k TPM",
        "max_output_tokens": 4096,
    },
    {
        "id": "openai/gpt-oss-20b",
        "raw_id": "openai/gpt-oss-20b",
        "name": "GPT OSS 20B (Equilibrado)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Versión equilibrada y rápida de GPT OSS alojada en Groq.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "Free Tier",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 1,000 RPD • 8k TPM",
        "max_output_tokens": 4096,
    },
    {
        "id": "whisper-large-v3",
        "raw_id": "whisper-large-v3",
        "name": "Whisper Large v3 (Groq Cloud)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Transcripción de audio ultrarrápida impulsada por chips LPU de Groq con la más alta precisión.",
        "context_window": "Audio (hasta 25MB)",
        "context_length": 0,
        "badge": "Recomendado Cloud (Free Tier)",
        "task_type": "transcription",
        "task_label": "Transcripción y Voz",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 14,400 RPD",
    },
    {
        "id": "whisper-large-v3-turbo",
        "raw_id": "whisper-large-v3-turbo",
        "name": "Whisper Large v3 Turbo (Groq Cloud)",
        "provider": "groq",
        "provider_name": "Groq Cloud",
        "description": "Versión Turbo de Whisper en Groq optimizada para latencia ultra baja y velocidad extrema.",
        "context_window": "Audio (hasta 25MB)",
        "context_length": 0,
        "badge": "Ultra Rápido (Free Tier)",
        "task_type": "transcription",
        "task_label": "Transcripción y Voz",
        "is_free": True,
        "tier_type": "free",
        "pricing_prompt": 0.0,
        "pricing_completion": 0.0,
        "pricing_label": "$0.00 (Gratuito en Groq Cloud)",
        "rate_limits": "30 RPM • 14,400 RPD",
    },
    # Claude models
    {
        "id": "claude-3-5-haiku-latest",
        "raw_id": "claude-3-5-haiku-latest",
        "name": "Claude 3.5 Haiku (Recomendado)",
        "provider": "claude",
        "provider_name": "Anthropic Claude",
        "description": "Modelo veloz y preciso de Anthropic con alta velocidad de respuesta y excelente razonamiento.",
        "context_window": "200k tokens",
        "context_length": 200000,
        "badge": "Ultra Rápido",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.8,
        "pricing_completion": 4.0,
        "pricing_label": "$0.80 / 1M input • $4.00 / 1M output",
        "rate_limits": "Tier 1: 50 RPM • 50k TPM",
    },
    {
        "id": "claude-3-5-sonnet-latest",
        "raw_id": "claude-3-5-sonnet-latest",
        "name": "Claude 3.5 Sonnet (Razonamiento Superior)",
        "provider": "claude",
        "provider_name": "Anthropic Claude",
        "description": "Líder en benchmarks de ingeniería de software, comprensión de requerimientos técnicos y QA.",
        "context_window": "200k tokens",
        "context_length": 200000,
        "badge": "Estado del Arte",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 3.0,
        "pricing_completion": 15.0,
        "pricing_label": "$3.00 / 1M input • $15.00 / 1M output",
        "rate_limits": "Tier 1: 50 RPM • 40k TPM",
    },
    {
        "id": "claude-3-7-sonnet-20250219",
        "raw_id": "claude-3-7-sonnet-20250219",
        "name": "Claude 3.7 Sonnet (Hybrid Reasoning)",
        "provider": "claude",
        "provider_name": "Anthropic Claude",
        "description": "El modelo insignia más avanzado de Anthropic con pensamiento híbrido adaptativo.",
        "context_window": "200k tokens",
        "context_length": 200000,
        "badge": "Frontier 3.7",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 3.0,
        "pricing_completion": 15.0,
        "pricing_label": "$3.00 / 1M input • $15.00 / 1M output",
        "rate_limits": "Tier 1: 50 RPM • 40k TPM",
    },
    # OpenAI models
    {
        "id": "gpt-4o-mini",
        "raw_id": "gpt-4o-mini",
        "name": "GPT-4o Mini (Económico y Rápido)",
        "provider": "openai",
        "provider_name": "OpenAI",
        "description": "Modelo inteligente, eficiente y de bajo costo de OpenAI para tareas cotidianas y QA.",
        "context_window": "128k tokens",
        "context_length": 128000,
        "badge": "Recomendado OpenAI",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.15,
        "pricing_completion": 0.60,
        "pricing_label": "$0.15 / 1M input • $0.60 / 1M output",
        "rate_limits": "Tier 1: 500 RPM • 200k TPM",
    },
    {
        "id": "gpt-4o",
        "raw_id": "gpt-4o",
        "name": "GPT-4o (Omni Multimodal)",
        "provider": "openai",
        "provider_name": "OpenAI",
        "description": "Modelo insignia multimodal de OpenAI con alta capacidad de comprensión y generación.",
        "context_window": "128k tokens",
        "context_length": 128000,
        "badge": "Flagship OpenAI",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 2.50,
        "pricing_completion": 10.00,
        "pricing_label": "$2.50 / 1M input • $10.00 / 1M output",
        "rate_limits": "Tier 1: 500 RPM • 30k TPM",
    },
    {
        "id": "o3-mini",
        "raw_id": "o3-mini",
        "name": "o3-mini (Razonamiento STEM y Código)",
        "provider": "openai",
        "provider_name": "OpenAI",
        "description": "Modelo especializado en razonamiento complejo, código y resolución de problemas técnicos.",
        "context_window": "200k tokens",
        "context_length": 200000,
        "badge": "Reasoning STEM",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 1.10,
        "pricing_completion": 4.40,
        "pricing_label": "$1.10 / 1M input • $4.40 / 1M output",
        "rate_limits": "Tier 1: 100 RPM • 100k TPM",
    },
    {
        "id": "whisper-1",
        "raw_id": "whisper-1",
        "name": "Whisper 1 (OpenAI Audio)",
        "provider": "openai",
        "provider_name": "OpenAI",
        "description": "Modelo de transcripción de voz oficial de OpenAI Audio API.",
        "context_window": "Audio (hasta 25MB)",
        "context_length": 0,
        "badge": "OpenAI Audio",
        "task_type": "transcription",
        "task_label": "Transcripción y Voz",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.006,
        "pricing_completion": 0.0,
        "pricing_label": "$0.006 por minuto de audio",
        "rate_limits": "50 RPM",
    },
    # Gemini models
    {
        "id": "gemini-1.5-flash",
        "raw_id": "gemini-1.5-flash",
        "name": "Gemini 1.5 Flash (Gran Contexto)",
        "provider": "gemini",
        "provider_name": "Google Gemini",
        "description": "Modelo rápido de Google con ventana de contexto de 1M de tokens y excelente soporte multimodal.",
        "context_window": "1M tokens",
        "context_length": 1048576,
        "badge": "1M Context",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.075,
        "pricing_completion": 0.30,
        "pricing_label": "$0.075 / 1M input • $0.30 / 1M output",
        "rate_limits": "15 RPM • 1M TPM (Free Tier disponible)",
    },
    {
        "id": "gemini-2.0-flash",
        "raw_id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash (Next-Gen)",
        "provider": "gemini",
        "provider_name": "Google Gemini",
        "description": "Modelo de nueva generación de Google con velocidad en tiempo real y alta fidelidad.",
        "context_window": "1M tokens",
        "context_length": 1048576,
        "badge": "Next-Gen Flash",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.10,
        "pricing_completion": 0.40,
        "pricing_label": "$0.10 / 1M input • $0.40 / 1M output",
        "rate_limits": "15 RPM • 1M TPM",
    },
    # DeepSeek models
    {
        "id": "deepseek-chat",
        "raw_id": "deepseek-chat",
        "name": "DeepSeek V3 (Chat & Redacción)",
        "provider": "deepseek",
        "provider_name": "DeepSeek",
        "description": "Modelo de lenguaje avanzado de DeepSeek con arquitectura MoE de alta eficiencia.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "DeepSeek V3",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.28,
        "pricing_completion": 0.42,
        "pricing_label": "$0.28 / 1M input • $0.42 / 1M output",
        "rate_limits": "60 RPM",
    },
    {
        "id": "deepseek-reasoner",
        "raw_id": "deepseek-reasoner",
        "name": "DeepSeek R1 (Razonamiento Profundo)",
        "provider": "deepseek",
        "provider_name": "DeepSeek",
        "description": "Modelo de razonamiento lógico y matemático por cadena de pensamiento de DeepSeek.",
        "context_window": "128k tokens",
        "context_length": 131072,
        "badge": "DeepSeek R1",
        "task_type": "chat_writing",
        "task_label": "Redacción y Chat",
        "is_free": False,
        "tier_type": "paid",
        "pricing_prompt": 0.55,
        "pricing_completion": 2.19,
        "pricing_label": "$0.55 / 1M input • $2.19 / 1M output",
        "rate_limits": "60 RPM",
    },
]


async def fetch_litellm_cost_map(timeout_seconds: float = 6.0) -> tuple[dict[str, Any], str]:
    """Fetch latest LiteLLM model cost map asynchronously.
    
    Falls back gracefully to the bundled LiteLLM cost map if network is unavailable.
    """
    try:
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
    except Exception as exc:
        logger.debug(f"Remote LiteLLM cost map fetch skipped/failed ({exc}); using bundled cost map")

    # Offline / local fallback
    local_map: dict[str, Any] = {}
    try:
        if hasattr(litellm, "model_cost") and isinstance(litellm.model_cost, dict):
            local_map = dict(litellm.model_cost)
    except Exception as exc:
        logger.debug(f"Failed to access litellm.model_cost: {exc}")

    return local_map, "bundled_litellm"


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


async def sync_frontier_models_catalog(force_remote: bool = False) -> dict[str, Any]:
    """Synchronize frontier model catalog with the latest LiteLLM database.
    
    Enriches context windows, max tokens, and pricing for all frontier models.
    Saves the updated catalog to USER_DATA_DIR / "ai" / "models_catalog.json".
    """
    global _last_sync_result
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cost_map, source = await fetch_litellm_cost_map(timeout_seconds=8.0 if force_remote else 5.0)

        target_file = CATALOG_FILE
        existing_data: list[dict[str, Any]] = []

        if target_file.exists():
            try:
                existing_data = json.loads(target_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not parse existing user catalog at {target_file}: {e}")

        if not existing_data and FALLBACK_CATALOG_FILE.exists():
            try:
                existing_data = json.loads(FALLBACK_CATALOG_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not parse fallback catalog: {e}")

        # Index existing models by id
        model_dict: dict[str, dict[str, Any]] = {}
        for item in existing_data:
            if isinstance(item, dict) and "id" in item:
                if item.get("provider") not in ("builtin", "local", "faster-whisper", "moonshine", "onnx"):
                    model_dict[item["id"]] = dict(item)

        # Merge known frontier models if not present
        for km in KNOWN_FRONTIER_MODELS:
            mid = km["id"]
            if mid not in model_dict:
                model_dict[mid] = dict(km)

        # Enrich each frontier model with LiteLLM specs
        for mid, model_item in model_dict.items():
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

        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(json.dumps(validated_list, indent=2, ensure_ascii=False), encoding="utf-8")

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
