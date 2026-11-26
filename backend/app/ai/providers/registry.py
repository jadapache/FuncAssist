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
  fallback_models: list[str] = field(default_factory=list)
  fast_model: str = ""
  supports_prompt_cache: bool = False
  supports_tools: bool = True


PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
  "groq": ProviderSpec(
    id="groq",
    name="Groq Cloud",
    litellm_prefix="groq",
    config_key="groq_api_key",
    # Last-resort names only: the effective defaults are picked from the synced catalog
    # (app.ai.catalog.pick_model) so retired models are never used.
    default_model="openai/gpt-oss-120b",
    fast_model="openai/gpt-oss-20b",
    default_max_tokens=4096,
  ),
  "gemini": ProviderSpec(
    id="gemini",
    name="Google Gemini",
    litellm_prefix="gemini",
    config_key="gemini_api_key",
    default_model="gemini-2.5-flash",
    fast_model="gemini-2.5-flash",
    aliases=("google",),
    default_max_tokens=8192,
    supports_prompt_cache=True,
  ),
  "claude": ProviderSpec(
    id="claude",
    name="Anthropic Claude",
    litellm_prefix="anthropic",
    config_key="claude_api_key",
    default_model="claude-sonnet-4-5",
    fast_model="claude-haiku-4-5",
    aliases=("anthropic",),
    default_max_tokens=8192,
    supports_prompt_cache=True,
  ),
  "openai": ProviderSpec(
    id="openai",
    name="OpenAI",
    litellm_prefix="",
    config_key="openai_api_key",
    default_model="gpt-4o",
    fast_model="gpt-4o-mini",
    default_max_tokens=16384,
    supports_prompt_cache=True,
  ),
  "ollama_remote": ProviderSpec(
    id="ollama_remote",
    name="Ollama Remote",
    litellm_prefix="ollama_chat",
    default_base_url=None,
    default_model="qwen2.5:2b",
    fast_model="qwen2.5:2b",
    is_local=False,
    aliases=("ollama",),
  ),
  "openrouter": ProviderSpec(
    id="openrouter",
    name="OpenRouter",
    litellm_prefix="openrouter",
    config_key="openrouter_api_key",
    default_model="meta-llama/llama-3.3-70b-instruct",
    fast_model="meta-llama/llama-3.1-8b-instruct",
  ),
  "deepseek": ProviderSpec(
    id="deepseek",
    name="DeepSeek",
    litellm_prefix="deepseek",
    config_key="deepseek_api_key",
    default_model="deepseek-chat",
    fast_model="deepseek-chat",
    supports_prompt_cache=True,
  ),
}


def find_provider_spec(identifier: str) -> ProviderSpec | None:
  clean = (identifier or "").strip().lower()
  if clean in FORBIDDEN_BACKEND_PROVIDERS:
    return None

  if clean in PROVIDER_REGISTRY:
    return PROVIDER_REGISTRY[clean]

  for spec in PROVIDER_REGISTRY.values():
    if clean in spec.aliases:
      return spec

  return None


def register_provider_spec(spec: ProviderSpec) -> None:
  PROVIDER_REGISTRY[spec.id] = spec


def resolve_model_max_tokens(provider_id: str, model_name: str, requested_max: int | None = None, is_stream: bool = False) -> int:
  prov_clean = (provider_id or "").strip().lower()
  spec = find_provider_spec(prov_clean)
  model_clean = (model_name or (spec.default_model if spec else "")).strip()

  ceiling = _catalog_output_limit(prov_clean, model_clean)
  if ceiling is None and spec:
    ceiling = spec.default_max_tokens
  return _clamp_max_tokens(requested_max, ceiling, is_stream)


def _clamp_max_tokens(requested: int | None, ceiling: int | None, is_stream: bool) -> int:
  """The requested limit capped by the ceiling; the ceiling or a default when none is requested."""
  known = [limit for limit in (requested, ceiling) if limit is not None]
  if known:
    return max(1, min(known))
  return 8192 if is_stream else 4096


def _catalog_output_limit(provider: str, model: str) -> int | None:
  """Max output tokens of the first catalog entry matching `provider`/`model` that declares one."""
  bare = model.split("/")[-1] if "/" in model else None
  try:
    from app.ai.catalog import load_local_catalog

    for entry in load_local_catalog():
      names = (entry.id, entry.raw_id)
      if entry.provider == provider and (model in names or (bare and bare in names)) and entry.max_output_tokens:
        return entry.max_output_tokens
  except Exception:
    pass
  return None
