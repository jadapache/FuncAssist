"""Resolve configured AI provider from local settings + env using ProviderSpec registry."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from app.ai.catalog import pick_model
from app.ai.endpoint_security import validate_remote_endpoint_url
from app.ai.providers.base import AIProvider
from app.ai.providers.implementations import LiteLLMProvider
from app.ai.providers.registry import FORBIDDEN_BACKEND_PROVIDERS, find_provider_spec
from app.core.storage import load_app_settings, load_user_ai_settings


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
  if user_id is None:
    _PROVIDER_CACHE.clear()
  else:
    keys_to_del = [k for k in _PROVIDER_CACHE if k[0] == user_id]
    for k in keys_to_del:
      _PROVIDER_CACHE.pop(k, None)


# Setting name, environment variable used when the user has not stored one.
_OPTIONAL_ENV = (
  ("provider", "AI_PROVIDER"),
  ("model", "AI_MODEL"),
  ("transcription_provider", "AI_TRANSCRIPTION_PROVIDER"),
  ("transcription_model", "AI_TRANSCRIPTION_MODEL"),
  ("voice_command_provider", "AI_VOICE_COMMAND_PROVIDER"),
  ("voice_command_model", "AI_VOICE_COMMAND_MODEL"),
  ("ollama_base_url", "OLLAMA_BASE_URL"),
  ("fast_model", "AI_FAST_MODEL"),
)
_KEY_ENV = (
  ("openai_api_key", "OPENAI_API_KEY"),
  ("claude_api_key", "ANTHROPIC_API_KEY"),
  ("groq_api_key", "GROQ_API_KEY"),
  ("gemini_api_key", "GEMINI_API_KEY"),
  ("openrouter_api_key", "OPENROUTER_API_KEY"),
  ("deepseek_api_key", "DEEPSEEK_API_KEY"),
)


def _stored_settings(user_id: Optional[str]) -> dict[str, Any]:
  return load_user_ai_settings(user_id) if user_id else (load_app_settings().get("ai") or {})


def _api_keys(ai: dict[str, Any]) -> dict[str, str]:
  """API keys: stored value, else environment variable, else empty."""
  keys = {name: ai.get(name) or os.getenv(env, "") for name, env in _KEY_ENV}
  # Transcription uses the general key of the same provider when it has no key of its own.
  keys["transcription_groq_api_key"] = ai.get("transcription_groq_api_key") or keys["groq_api_key"]
  keys["transcription_openai_api_key"] = ai.get("transcription_openai_api_key") or keys["openai_api_key"]
  return keys


def get_ai_settings(user_id: Optional[str] = None) -> dict[str, Any]:
  """Load AI settings for a specific user from storage, falling back to global settings."""
  ai = _stored_settings(user_id)
  return {
    **{name: ai.get(name) or os.getenv(env) or None for name, env in _OPTIONAL_ENV},
    **_api_keys(ai),
    "fallback_models": _normalize_fallbacks(ai.get("fallback_models") or os.getenv("AI_FALLBACK_MODELS") or []),
  }


def _is_ollama(spec: Any) -> bool:
  return spec.id == "ollama_remote" or "ollama" in spec.aliases


def _require_backend_provider(target_name: str) -> None:
  if target_name in FORBIDDEN_BACKEND_PROVIDERS:
    raise ValueError(
      f"El proveedor '{target_name}' no se ejecuta en el backend. "
      "La inferencia local se ejecuta exclusivamente en el navegador mediante WebLLM."
    )


def _requested_model(model_name: str | None, config: dict[str, Any], same_provider: bool) -> str:
  """The model named in the request, else the user's configured one (their own provider only)."""
  return model_name or (config.get("model") if same_provider else None) or ""


def _require_supported_model(model: str) -> None:
  if model.lower().endswith(".gguf"):
    raise ValueError("Modelos GGUF no están admitidos en el backend.")


def _fallbacks_for(config: dict[str, Any], tier: str, same_provider: bool) -> list[str]:
  """Fallbacks belong to the main tier only: the fast tier is already the cheap path, and the
  user's list refers to their main provider's models."""
  return (config.get("fallback_models") or []) if tier == "main" and same_provider else []


def _require_known_provider(spec: Any, target_name: str) -> None:
  if not spec:
    raise ValueError(
      f"No valid AI provider found for '{target_name}'. "
      "Configure provider in Settings (groq | gemini | claude | openai | ollama_remote | openrouter | deepseek)."
    )


def _choose_model(
  spec: Any, config: dict[str, Any], tier: str, model_name: str | None, main_model: str | None,
  user_model: str, same_provider: bool,
) -> tuple[str, str | None]:
  """(model to use, model to retry with if it no longer exists); the retry applies to the fast tier only."""
  resolved_main = main_model or user_model or pick_model(spec.id, "main", spec.default_model) or spec.default_model
  if tier != "fast":
    return resolved_main, None
  chosen = _fast_model(spec, config, model_name, same_provider) or resolved_main
  return chosen, (resolved_main if chosen != resolved_main else None)


def _fast_model(spec: Any, config: dict[str, Any], model_name: str | None, same_provider: bool) -> str | None:
  """Requested model, else the user's fast model (their own provider only), else the catalog's pick."""
  configured_fast = config.get("fast_model") if same_provider else None
  return model_name or configured_fast or pick_model(spec.id, "fast", spec.fast_model)


def _cached_provider(cache_key: tuple[Any, ...], build: Callable[[], AIProvider]) -> AIProvider:
  if cache_key not in _PROVIDER_CACHE:
    _PROVIDER_CACHE[cache_key] = build()
  return _PROVIDER_CACHE[cache_key]


def _ollama_provider(
  spec: Any, config: dict[str, Any], base_url: str | None, cache_prefix: tuple[Any, ...], fallbacks: list[str],
  not_found_fallback: str | None,
) -> AIProvider:
  target_base_url = (base_url or config.get("ollama_base_url") or "").rstrip("/")
  if not target_base_url:
    raise ValueError("Ollama remoto requiere una URL HTTPS explícita.")
  ok, err = validate_remote_endpoint_url(target_base_url)
  if not ok:
    raise ValueError(f"URL de Ollama remoto no permitida: {err}")
  user_id, target_name, chosen_model, fb_key = cache_prefix
  cache_key = (user_id, target_name, chosen_model, "", target_base_url, fb_key)
  return _cached_provider(cache_key, lambda: LiteLLMProvider(
    spec, base_url=target_base_url, default_model=chosen_model,
    fallback_models=fallbacks, not_found_fallback=not_found_fallback,
  ))


def _api_key_provider(
  spec: Any, config: dict[str, Any], api_key: str | None, base_url: str | None, cache_prefix: tuple[Any, ...],
  fallbacks: list[str], not_found_fallback: str | None,
) -> AIProvider:
  stored_key = config.get(spec.config_key) if spec.config_key else None
  env_key = os.getenv(spec.env_key) if spec.env_key else None
  key = api_key or stored_key or env_key or ""
  if not key:
    env_hint = f" ({spec.env_key})" if spec.env_key else ""
    raise ValueError(f"{spec.name} is selected but API key{env_hint} is missing.")
  user_id, target_name, chosen_model, fb_key = cache_prefix
  cache_key = (user_id, target_name, chosen_model, key, base_url, fb_key)
  return _cached_provider(cache_key, lambda: LiteLLMProvider(
    spec, api_key=key, default_model=chosen_model,
    fallback_models=fallbacks, not_found_fallback=not_found_fallback,
  ))


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
  _require_backend_provider(target_name)

  spec = find_provider_spec(target_name)
  same_provider = bool(spec) and find_provider_spec(configured_provider) is spec
  user_model = _requested_model(model_name, config, same_provider)
  _require_supported_model(user_model)
  _require_known_provider(spec, target_name)

  chosen_model, not_found_fallback = _choose_model(spec, config, tier, model_name, main_model, user_model, same_provider)
  fallbacks = _fallbacks_for(config, tier, same_provider)
  cache_prefix = (user_id, target_name, chosen_model, (tuple(fallbacks), not_found_fallback))

  if _is_ollama(spec):
    return _ollama_provider(spec, config, base_url, cache_prefix, fallbacks, not_found_fallback)
  return _api_key_provider(spec, config, api_key, base_url, cache_prefix, fallbacks, not_found_fallback)
