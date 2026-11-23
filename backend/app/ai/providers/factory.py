"""Resolve configured AI provider from local settings + env using ProviderSpec registry."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Any, Optional

from app.ai.catalog import pick_model
from app.ai.endpoint_security import validate_remote_endpoint_url
from app.ai.providers.base import AIProvider
from app.ai.providers.implementations import LiteLLMProvider
from app.ai.providers.registry import FORBIDDEN_BACKEND_PROVIDERS, find_provider_spec
from app.core.storage import load_app_settings, load_user_ai_settings

_CACHE_KEY_SALT = secrets.token_bytes(32)

_PROVIDER_CACHE: dict[tuple[Any, ...], AIProvider] = {}
MAX_FALLBACK_MODELS = 3


def _normalize_fallbacks(raw: Any) -> list[str]:
  """Accept a list or comma-separated string; keep unique non-empty names, capped."""
  if isinstance(raw, str):
    raw = raw.split(",")
  if not isinstance(raw, (list, tuple)):
    return []
  cleaned = [str(m).strip() for m in raw if isinstance(m, str) and str(m).strip()]
  return list(dict.fromkeys(cleaned))[:MAX_FALLBACK_MODELS]


def clear_provider_cache(user_id: str | None = None) -> None:
  """Invalidate cached providers (all or for a specific user)."""
  global _PROVIDER_CACHE
  if user_id is None:
    _PROVIDER_CACHE.clear()
  else:
    keys_to_del = [k for k in _PROVIDER_CACHE if k[0] == user_id]
    for k in keys_to_del:
      _PROVIDER_CACHE.pop(k, None)


def get_ai_settings(user_id: Optional[str] = None) -> dict[str, Any]:
  """Load AI settings for a specific user from storage, falling back to global settings."""
  ai = load_user_ai_settings(user_id) if user_id else (load_app_settings().get("ai") or {})
  return {
    "provider": ai.get("provider") or os.getenv("AI_PROVIDER") or None,
    "model": ai.get("model") or os.getenv("AI_MODEL") or None,
    "transcription_provider": ai.get("transcription_provider") or os.getenv("AI_TRANSCRIPTION_PROVIDER") or None,
    "transcription_model": ai.get("transcription_model") or os.getenv("AI_TRANSCRIPTION_MODEL") or None,
    "voice_command_provider": ai.get("voice_command_provider") or os.getenv("AI_VOICE_COMMAND_PROVIDER") or None,
    "voice_command_model": ai.get("voice_command_model") or os.getenv("AI_VOICE_COMMAND_MODEL") or None,
    "openai_api_key": ai.get("openai_api_key") or os.getenv("OPENAI_API_KEY", ""),
    "claude_api_key": ai.get("claude_api_key") or os.getenv("ANTHROPIC_API_KEY", ""),
    "groq_api_key": ai.get("groq_api_key") or os.getenv("GROQ_API_KEY", ""),
    "gemini_api_key": ai.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", ""),
    "transcription_groq_api_key": ai.get("transcription_groq_api_key") or ai.get("groq_api_key") or os.getenv("GROQ_API_KEY", ""),
    "transcription_openai_api_key": ai.get("transcription_openai_api_key") or ai.get("openai_api_key") or os.getenv("OPENAI_API_KEY", ""),
    "ollama_base_url": ai.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL") or None,
    "fallback_models": _normalize_fallbacks(ai.get("fallback_models") or os.getenv("AI_FALLBACK_MODELS") or []),
    "fast_model": ai.get("fast_model") or os.getenv("AI_FAST_MODEL") or None,
  }


def resolve_provider(
  provider_name: str | None = None,
  model_name: str | None = None,
  api_key: str | None = None,
  base_url: str | None = None,
  user_id: str | None = None,
  tier: str = "main",
  main_model: str | None = None,
) -> AIProvider:
  """Build (or reuse) the provider for a request.

  Model resolution, most specific first:
  - main tier: `model_name` → configured model → catalog pick for the tier → registry default.
  - fast tier: `model_name` → configured fast model → catalog pick for the tier → the main model.
    `main_model` lets the caller name the main model actually in use (e.g. a per-request override);
    the fast provider retries once with it if its own model no longer exists.
  User settings (model, fast model, fallbacks) apply only when the request targets the configured
  provider: they name that provider's models.
  """
  config = get_ai_settings(user_id=user_id)
  configured_provider = (config.get("provider") or "").lower()
  target_name = (provider_name or configured_provider).lower()

  if target_name in FORBIDDEN_BACKEND_PROVIDERS:
    raise ValueError(
      f"El proveedor '{target_name}' no se ejecuta en el backend. "
      "La inferencia local se ejecuta exclusivamente en el navegador mediante WebLLM."
    )

  spec = find_provider_spec(target_name)
  same_provider = bool(spec) and find_provider_spec(configured_provider) is spec
  user_model = model_name or (config.get("model") if same_provider else None) or ""
  if user_model.lower().endswith(".gguf"):
    raise ValueError("Modelos GGUF no están admitidos en el backend.")

  if not spec:
    raise ValueError(
      f"No valid AI provider found for '{target_name}'. "
      "Configure provider in Settings (groq | gemini | claude | openai | ollama_remote | openrouter | deepseek)."
    )

  resolved_main = main_model or user_model or pick_model(spec.id, "main", spec.default_model) or spec.default_model
  not_found_fallback: str | None = None
  if tier == "fast":
    configured_fast = config.get("fast_model") if same_provider else None
    chosen_model = model_name or configured_fast or pick_model(spec.id, "fast", spec.fast_model) or resolved_main
    if chosen_model != resolved_main:
      not_found_fallback = resolved_main
  else:
    chosen_model = resolved_main

  # Fallbacks belong to the main tier only: the fast tier is already the cheap path,
  # and the user's list refers to their main provider's models.
  fallbacks = (config.get("fallback_models") or []) if tier == "main" and same_provider else []
  fb_key = (tuple(fallbacks), not_found_fallback)

  if spec.id == "ollama_remote" or "ollama" in spec.aliases:
    target_base_url = (base_url or config.get("ollama_base_url") or "").rstrip("/")
    if not target_base_url:
      raise ValueError("Ollama remoto requiere una URL HTTPS explícita.")
    ok, err = validate_remote_endpoint_url(target_base_url)
    if not ok:
      raise ValueError(f"URL de Ollama remoto no permitida: {err}")
    cache_key = (user_id, target_name, chosen_model, "", target_base_url, fb_key)
    if cache_key in _PROVIDER_CACHE:
      return _PROVIDER_CACHE[cache_key]
    provider = LiteLLMProvider(
      spec,
      base_url=target_base_url,
      default_model=chosen_model,
      fallback_models=fallbacks,
      not_found_fallback=not_found_fallback,
    )
    _PROVIDER_CACHE[cache_key] = provider
    return provider

  key = (
    api_key
    or (config.get(spec.config_key) if spec.config_key else None)
    or (os.getenv(spec.env_key) if spec.env_key else None)
    or ""
  )
  if not key:
    env_hint = f" ({spec.env_key})" if spec.env_key else ""
    raise ValueError(f"{spec.name} is selected but API key{env_hint} is missing.")

  # Keyed digest: the cache never holds a plain, offline-guessable hash of the API key.
  key_hash = hmac.new(_CACHE_KEY_SALT, key.encode("utf-8"), hashlib.sha256).hexdigest()
  cache_key = (user_id, target_name, chosen_model, key_hash, base_url, fb_key)
  if cache_key in _PROVIDER_CACHE:
    return _PROVIDER_CACHE[cache_key]

  provider = LiteLLMProvider(
    spec,
    api_key=key,
    default_model=chosen_model,
    fallback_models=fallbacks,
    not_found_fallback=not_found_fallback,
  )
  _PROVIDER_CACHE[cache_key] = provider
  return provider
