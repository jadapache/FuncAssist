"""Declarative provider registry inspired by nanobot architecture.

Defines ProviderSpec as the single source of truth for all supported LLM providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FORBIDDEN_BACKEND_PROVIDERS = frozenset([
    "builtin",
    "local",
    "faster-whisper",
    "moonshine",
    "onnx",
])


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
    config_key="groq_api_key",
    default_model="llama-3.3-70b-versatile",
    default_max_tokens=4096,
  ),
  "gemini": ProviderSpec(
    id="gemini",
    name="Google Gemini",
    litellm_prefix="gemini",
    config_key="gemini_api_key",
    default_model="gemini-2.5-flash",
    aliases=("google",),
    default_max_tokens=8192,
  ),
  "claude": ProviderSpec(
    id="claude",
    name="Anthropic Claude",
    litellm_prefix="anthropic",
    config_key="claude_api_key",
    default_model="claude-3-5-haiku-latest",
    aliases=("anthropic",),
    default_max_tokens=8192,
  ),
  "openai": ProviderSpec(
    id="openai",
    name="OpenAI",
    litellm_prefix="",
    config_key="openai_api_key",
    default_model="gpt-4o-mini",
    default_max_tokens=16384,
  ),
  "ollama_remote": ProviderSpec(
    id="ollama_remote",
    name="Ollama Remote",
    litellm_prefix="ollama_chat",
    default_base_url=None,
    default_model="qwen2.5:2b",
    is_local=False,
    aliases=("ollama",),
  ),
  "openrouter": ProviderSpec(
    id="openrouter",
    name="OpenRouter",
    litellm_prefix="openrouter",
    config_key="openrouter_api_key",
    default_model="meta-llama/llama-3.3-70b-instruct",
  ),
  "deepseek": ProviderSpec(
    id="deepseek",
    name="DeepSeek",
    litellm_prefix="deepseek",
    config_key="deepseek_api_key",
    default_model="deepseek-chat",
  ),
}


def find_provider_spec(identifier: str) -> ProviderSpec | None:
  clean = (identifier or "").strip().lower()
  if not clean or clean in FORBIDDEN_BACKEND_PROVIDERS:
    return None

  if clean in PROVIDER_REGISTRY:
    return PROVIDER_REGISTRY[clean]

  for spec in PROVIDER_REGISTRY.values():
    if clean in spec.aliases:
      return spec

  return None


def register_provider_spec(spec: ProviderSpec) -> None:
  PROVIDER_REGISTRY[spec.id] = spec


def resolve_model_max_tokens(
  provider_id: str,
  model_name: str,
  requested_max: int | None = None,
  is_stream: bool = False,
) -> int:
  prov_clean = (provider_id or "").strip().lower()
  spec = find_provider_spec(prov_clean)
  model_clean = (model_name or (spec.default_model if spec else "")).strip()

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

  ceiling = model_limit if model_limit is not None else (spec.default_max_tokens if spec else None)

  if ceiling is not None:
    if requested_max is not None:
      return max(1, min(requested_max, ceiling))
    return max(1, ceiling)

  if requested_max is not None:
    return max(1, requested_max)

  return 8192 if is_stream else 4096
