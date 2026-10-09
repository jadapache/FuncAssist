"""Declarative provider registry inspired by nanobot architecture.

Defines ProviderSpec as the single source of truth for all supported LLM providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
  id: str
  name: str
  litellm_prefix: str
  env_key: str | None = None
  config_key: str | None = None
  default_model: str = ""
  default_base_url: str | None = None
  is_local: bool = False
  aliases: tuple[str, ...] = ()
  default_max_tokens: int | None = None
  extra_kwargs: dict[str, Any] = field(default_factory=dict)


PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
  "groq": ProviderSpec(
    id="groq",
    name="Groq Cloud",
    litellm_prefix="groq",
    env_key="GROQ_API_KEY",
    config_key="groq_api_key",
    default_model="llama-3.3-70b-versatile",
    default_max_tokens=4096,
  ),
  "gemini": ProviderSpec(
    id="gemini",
    name="Google Gemini",
    litellm_prefix="gemini",
    env_key="GEMINI_API_KEY",
    config_key="gemini_api_key",
    default_model="gemini-2.5-flash",
    aliases=("google",),
  ),
  "claude": ProviderSpec(
    id="claude",
    name="Anthropic Claude",
    litellm_prefix="anthropic",
    env_key="ANTHROPIC_API_KEY",
    config_key="claude_api_key",
    default_model="claude-3-5-haiku-latest",
    aliases=("anthropic",),
  ),
  "openai": ProviderSpec(
    id="openai",
    name="OpenAI",
    litellm_prefix="",
    env_key="OPENAI_API_KEY",
    config_key="openai_api_key",
    default_model="gpt-4o-mini",
  ),
  "ollama": ProviderSpec(
    id="ollama",
    name="Ollama",
    litellm_prefix="ollama_chat",
    default_base_url="http://127.0.0.1:11434",
    default_model="qwen2.5:2b",
    is_local=True,
    aliases=("builtin", "local"),
  ),
  "openrouter": ProviderSpec(
    id="openrouter",
    name="OpenRouter",
    litellm_prefix="openrouter",
    env_key="OPENROUTER_API_KEY",
    config_key="openrouter_api_key",
    default_model="meta-llama/llama-3.3-70b-instruct",
  ),
  "deepseek": ProviderSpec(
    id="deepseek",
    name="DeepSeek",
    litellm_prefix="deepseek",
    env_key="DEEPSEEK_API_KEY",
    config_key="deepseek_api_key",
    default_model="deepseek-chat",
  ),
}


def find_provider_spec(identifier: str) -> ProviderSpec | None:
  """Lookup provider spec by id or alias."""
  clean = (identifier or "").strip().lower()
  if not clean:
    return None

  if clean in PROVIDER_REGISTRY:
    return PROVIDER_REGISTRY[clean]

  for spec in PROVIDER_REGISTRY.values():
    if clean in spec.aliases:
      return spec

  return None


def register_provider_spec(spec: ProviderSpec) -> None:
  """Register or override a provider spec dynamically."""
  PROVIDER_REGISTRY[spec.id] = spec


def resolve_model_max_tokens(
  provider_id: str,
  model_name: str,
  requested_max: int | None = None,
  is_stream: bool = False,
) -> int:
  """Resolve effective max_tokens respecting provider and catalog-defined model ceilings."""
  prov_clean = (provider_id or "").strip().lower()
  spec = find_provider_spec(prov_clean)
  model_clean = (model_name or (spec.default_model if spec else "")).strip()

  # Check catalog metadata for model limit
  model_limit = None
  try:
    from app.ai.catalog import load_local_catalog

    catalog = load_local_catalog()
    for m in catalog:
      if m.provider == prov_clean and (
        m.id == model_clean
        or m.raw_id == model_clean
        or ("/" in model_clean and (m.id == model_clean.split("/")[-1] or m.raw_id == model_clean.split("/")[-1]))
      ):
        if m.max_output_tokens:
          model_limit = m.max_output_tokens
          break
  except Exception:
    pass

  default_limit = (spec.default_max_tokens if spec else None) or (8192 if is_stream else 4096)

  if model_limit is not None:
    if requested_max is not None:
      return max(1, min(requested_max, model_limit))
    return max(1, model_limit)

  if requested_max is not None:
    return max(1, requested_max)

  return max(1, default_limit)
