"""Unified LiteLLM provider implementation backed by ProviderSpec registry."""

from __future__ import annotations

import logging
import re
from typing import Any

import os
# Disable remote cost map fetch during standard execution
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm

from app.ai.providers.base import AICompletion, AIMessage, AIProvider
from app.ai.providers.registry import (
  ProviderSpec,
  find_provider_spec,
  resolve_model_max_tokens,
)

logger = logging.getLogger(__name__)

# Disable litellm telemetry and set quiet mode
litellm.telemetry = False
litellm.suppress_debug_info = True
litellm.set_verbose = False


def _handle_completion_error(err: Exception) -> Exception:
  err_str = str(err)
  if "reduce max_tokens" in err_str or "OTPM" in err_str or "output tokens per minute" in err_str:
    limit_match = re.search(r"Limit\s+(\d+)", err_str, re.IGNORECASE)
    req_match = re.search(r"Requested\s+(\d+)", err_str, re.IGNORECASE)
    req_tokens = req_match.group(1) if req_match else "solicitada"
    limit_tokens = limit_match.group(1) if limit_match else "establecido"
    return RuntimeError(
      f"La solicitud con {req_tokens} tokens supera el límite de {limit_tokens} tokens de salida para este modelo. "
      f"Te sugerimos seleccionar un modelo diferente en Configuración (Settings)."
    )
  return err


class LiteLLMProvider(AIProvider):
  id: str
  name: str
  spec: ProviderSpec

  def __init__(
    self,
    provider_id: str | ProviderSpec,
    api_key: str | None = None,
    base_url: str | None = None,
    default_model: str | None = None,
  ) -> None:
    if isinstance(provider_id, ProviderSpec):
      self.spec = provider_id
      self.id = self.spec.id
      self.name = self.spec.name
    else:
      found = find_provider_spec(provider_id)
      if found:
        self.spec = found
        self.id = found.id
        self.name = found.name
      else:
        self.id = provider_id
        self.name = provider_id.capitalize()
        self.spec = ProviderSpec(
          id=provider_id,
          name=self.name,
          litellm_prefix=provider_id,
        )

    self.api_key = api_key
    self.base_url = base_url or self.spec.default_base_url
    self.default_model = default_model or self.spec.default_model

  def _format_model_name(self, model: str) -> str:
    m = model.strip()
    prefix = self.spec.litellm_prefix

    # Special handling for Ollama
    if self.spec.id in {"ollama", "builtin", "local"} or prefix == "ollama_chat":
      if m.startswith("ollama/") or m.startswith("ollama_chat/"):
        return m
      return f"ollama_chat/{m}"

    # Special handling for OpenAI (LiteLLM accepts direct model names for openai)
    if self.spec.id == "openai" or prefix == "":
      if m.startswith("openai/"):
        return m[7:]
      return m

    # Special handling for Gemini/Google models prefix
    if self.spec.id in {"gemini", "google"}:
      if m.startswith("gemini/"):
        return m
      if m.startswith("models/"):
        return f"gemini/{m[7:]}"
      return f"gemini/{m}"

    # General prefix rule: if model already starts with prefix/, don't double prefix
    if prefix and m.startswith(f"{prefix}/"):
      return m

    return f"{prefix}/{m}" if prefix else m

  async def complete(
    self,
    messages: list[AIMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
  ) -> AICompletion:
    chosen_raw = model or self.default_model
    formatted_model = self._format_model_name(chosen_raw)

    kwargs: dict[str, Any] = {
      "model": formatted_model,
      "messages": [message.model_dump() for message in messages],
      **self.spec.extra_kwargs,
    }

    # Gemini 3+ models raise DeprecationWarning when temperature/top_p is passed explicitly
    if not (self.id == "gemini" or formatted_model.startswith("gemini/")):
      if "temperature" not in kwargs:
        kwargs["temperature"] = 0.2

    effective_max_tokens = resolve_model_max_tokens(
      self.id,
      chosen_raw,
      requested_max=max_tokens,
      is_stream=False,
    )
    kwargs["max_tokens"] = effective_max_tokens

    if self.api_key:
      kwargs["api_key"] = self.api_key
    if self.base_url:
      kwargs["api_base"] = self.base_url

    try:
      response = await litellm.acompletion(**kwargs)
    except Exception as err:
      raise _handle_completion_error(err) from err

    raw_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)

    text = ""
    if hasattr(response, "choices") and response.choices:
      choice = response.choices[0]
      if hasattr(choice, "message") and hasattr(choice.message, "content"):
        text = choice.message.content or ""

    clean_model_name = chosen_raw.split("/")[-1] if "/" in chosen_raw else chosen_raw
    return AICompletion(text=text, provider=self.id, model=clean_model_name, raw=raw_dict)

  async def complete_stream(
    self,
    messages: list[AIMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
  ):
    chosen_raw = model or self.default_model
    formatted_model = self._format_model_name(chosen_raw)

    kwargs: dict[str, Any] = {
      "model": formatted_model,
      "messages": [message.model_dump() for message in messages],
      "stream": True,
      **self.spec.extra_kwargs,
    }

    if not (self.id == "gemini" or formatted_model.startswith("gemini/")):
      if "temperature" not in kwargs:
        kwargs["temperature"] = 0.2

    effective_max_tokens = resolve_model_max_tokens(
      self.id,
      chosen_raw,
      requested_max=max_tokens,
      is_stream=True,
    )
    kwargs["max_tokens"] = effective_max_tokens

    if self.api_key:
      kwargs["api_key"] = self.api_key
    if self.base_url:
      kwargs["api_base"] = self.base_url

    try:
      response = await litellm.acompletion(**kwargs)
    except Exception as err:
      raise _handle_completion_error(err) from err

    async for chunk in response:
      if hasattr(chunk, "choices") and chunk.choices:
        choice = chunk.choices[0]
        if hasattr(choice, "delta") and hasattr(choice.delta, "content"):
          delta_content = choice.delta.content
          if delta_content:
            yield delta_content



# Backwards-compatible aliases mapping to the registry
class OpenAIProvider(LiteLLMProvider):
  def __init__(self, api_key: str, default_model: str = "gpt-4o-mini") -> None:
    super().__init__("openai", api_key=api_key, default_model=default_model)


class ClaudeProvider(LiteLLMProvider):
  def __init__(self, api_key: str, default_model: str = "claude-3-5-haiku-latest") -> None:
    super().__init__("claude", api_key=api_key, default_model=default_model)


class GroqProvider(LiteLLMProvider):
  def __init__(self, api_key: str, default_model: str = "llama-3.3-70b-versatile") -> None:
    super().__init__("groq", api_key=api_key, default_model=default_model)


class GeminiProvider(LiteLLMProvider):
  def __init__(self, api_key: str, default_model: str = "gemini-1.5-flash") -> None:
    super().__init__("gemini", api_key=api_key, default_model=default_model)


class OllamaProvider(LiteLLMProvider):
  def __init__(self, base_url: str = "http://127.0.0.1:11434", default_model: str = "qwen2.5:2b") -> None:
    super().__init__("ollama", base_url=base_url, default_model=default_model)
