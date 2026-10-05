"""Resolve configured AI provider from local settings + env using ProviderSpec registry."""

from __future__ import annotations

import os
from typing import Any

from app.ai.providers.base import AIProvider
from app.ai.providers.implementations import LiteLLMProvider
from app.ai.providers.registry import find_provider_spec
from app.core.storage import load_app_settings


def get_ai_settings() -> dict[str, Any]:
  """Load AI settings from storage"""
  settings = load_app_settings()
  ai = settings.get("ai") or {}
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
    "ollama_base_url": ai.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
  }


def resolve_provider(
  provider_name: str | None = None,
  model_name: str | None = None,
  api_key: str | None = None,
  base_url: str | None = None,
) -> AIProvider:
  config = get_ai_settings()
  target_name = (provider_name or config.get("provider") or "").lower()
  spec = find_provider_spec(target_name)

  if not spec:
    raise ValueError(
      f"No valid AI provider found for '{target_name}'. "
      "Configure provider in Settings (groq | gemini | claude | openai | ollama | openrouter | deepseek)."
    )

  chosen_model = model_name or config.get("model") or spec.default_model

  if spec.is_local:
    target_base_url = base_url or config.get("ollama_base_url") or spec.default_base_url
    return LiteLLMProvider(spec, base_url=target_base_url, default_model=chosen_model)

  # Cloud provider
  key = (
    api_key
    or (config.get(spec.config_key) if spec.config_key else None)
    or (os.getenv(spec.env_key) if spec.env_key else None)
    or ""
  )
  if not key:
    env_hint = f" ({spec.env_key})" if spec.env_key else ""
    raise ValueError(f"{spec.name} is selected but API key{env_hint} is missing.")

  return LiteLLMProvider(spec, api_key=key, default_model=chosen_model)
