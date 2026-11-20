"""Unified LiteLLM provider implementation backed by ProviderSpec registry."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
# Disable remote cost map fetch during standard execution
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm

from app.ai.errors import AIError
from app.ai.providers.base import AICompletion, AIMessage, AIProvider, ToolCall
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
  lower_err = err_str.lower()

  if isinstance(err, litellm.ContextWindowExceededError) or "contextwindowsizeexceeded" in lower_err or "context length" in lower_err or "context_window" in lower_err:
    return AIError(
      code="context_window_exceeded",
      user_message="La longitud del texto supera la ventana de contexto del modelo. Te sugerimos seleccionar un modelo con ventana extendida.",
      original_error=err,
    )

  if isinstance(err, litellm.RateLimitError) or "ratelimiterror" in lower_err or "rate limit" in lower_err or "429" in lower_err:
    wait_match = re.search(r"try again in ([0-9.]+s?)", err_str, re.IGNORECASE)
    wait_time = wait_match.group(1) if wait_match else "unos segundos"
    retry_sec = float(wait_match.group(1).rstrip("s")) if wait_match else None
    limit_match = re.search(r"Limit\s+(\d+)", err_str, re.IGNORECASE)
    req_match = re.search(r"Requested\s+(\d+)", err_str, re.IGNORECASE)

    if "otpm" in lower_err or "output tokens per minute" in lower_err:
      msg = f"Límite de tokens de salida por minuto (OTPM) alcanzado. Espera {wait_time} o selecciona otro modelo."
      if limit_match and req_match:
        msg = (
          f"Límite de tokens de salida por minuto (OTPM) alcanzado ({req_match.group(1)} solicitados, límite {limit_match.group(1)}). "
          f"Espera {wait_time} o selecciona un modelo con mayor cuota en Configuración."
        )
      return AIError(code="rate_limit", user_message=msg, retry_after=retry_sec, original_error=err)

    if "itpm" in lower_err or "input tokens per minute" in lower_err:
      msg = "El texto enviado supera el límite de tokens de entrada por minuto (ITPM) de este modelo."
      if limit_match and req_match:
        msg = f"El texto enviado ({req_match.group(1)} tokens) supera el límite de {limit_match.group(1)} tokens de entrada por minuto (ITPM)."
      return AIError(code="rate_limit", user_message=msg, retry_after=retry_sec, original_error=err)

    msg = f"Límite de peticiones por minuto alcanzado para este modelo. Por favor espera {wait_time} o selecciona otro modelo."
    if limit_match and req_match:
      msg = f"Límite de tasa de tokens por minuto (TPM) alcanzado ({req_match.group(1)} solicitados, límite {limit_match.group(1)}). Espera {wait_time}."
    return AIError(code="rate_limit", user_message=msg, retry_after=retry_sec, original_error=err)

  if isinstance(err, litellm.Timeout) or "timeout" in lower_err:
    return AIError(
      code="timeout",
      user_message="La llamada al modelo excedió el tiempo límite de espera. Inténtalo de nuevo.",
      original_error=err,
    )

  if isinstance(err, litellm.AuthenticationError) or "auth" in lower_err or "api key" in lower_err:
    return AIError(
      code="auth_error",
      user_message="Error de autenticación con el proveedor del modelo. Verifica tu API Key en Configuración.",
      original_error=err,
    )

  if isinstance(err, litellm.BadRequestError) or "badrequesterror" in lower_err:
    if "reduce max_tokens" in lower_err:
      limit_match = re.search(r"Limit\s+(\d+)", err_str, re.IGNORECASE)
      req_match = re.search(r"Requested\s+(\d+)", err_str, re.IGNORECASE)
      req_tokens = req_match.group(1) if req_match else "solicitada"
      limit_tokens = limit_match.group(1) if limit_match else "establecido"
      return AIError(
        code="max_tokens_exceeded",
        user_message=f"La solicitud con {req_tokens} tokens supera el límite de {limit_tokens} tokens de salida. Te sugerimos seleccionar otro modelo.",
        original_error=err,
      )
    return AIError(code="bad_request", user_message=f"Petición inválida al modelo: {err_str}", original_error=err)

  return err


# Providers whose streaming API reports usage when asked via stream_options.
_STREAM_USAGE_PROVIDERS = frozenset({"openai", "claude", "groq", "deepseek", "gemini", "openrouter"})
# Providers that need explicit cache breakpoints; the rest (OpenAI, Gemini, DeepSeek) cache
# stable prefixes implicitly, which only requires static-first message ordering.
_EXPLICIT_CACHE_PROVIDERS = frozenset({"claude"})
_MAX_CACHE_BREAKPOINTS = 4  # Anthropic limit per request


def _prompt_cache_enabled() -> bool:
  return os.getenv("AI_PROMPT_CACHE", "on").strip().lower() not in ("0", "off", "false", "no")


def _mark_cacheable(message: dict[str, Any]) -> bool:
  """Attach an ephemeral cache_control to the message's last text block."""
  content = message.get("content")
  if isinstance(content, str):
    if not content.strip():
      return False
    message["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    return True
  if isinstance(content, list):
    # Copy parts: the list is shared with the caller's AIMessage and must not be mutated.
    parts = [dict(p) if isinstance(p, dict) else p for p in content]
    for part in reversed(parts):
      if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
        part["cache_control"] = {"type": "ephemeral"}
        message["content"] = parts
        return True
  return False


def apply_cache_breakpoints(wire_messages: list[dict[str, Any]]) -> int:
  """Place cache breakpoints on the stable prefix of the conversation.

  Breakpoints: the last system message (system prompt + documentary context) and the last
  message before the current user turn (end of history). Returns how many were placed.
  """
  if not wire_messages:
    return 0
  targets: list[int] = []
  system_idx = [i for i, m in enumerate(wire_messages) if m.get("role") == "system"]
  if system_idx:
    targets.append(system_idx[-1])
  if len(wire_messages) >= 3 and wire_messages[-1].get("role") == "user":
    prev = len(wire_messages) - 2
    if prev not in targets and wire_messages[prev].get("role") in ("user", "assistant"):
      targets.append(prev)
  placed = 0
  for idx in targets[:_MAX_CACHE_BREAKPOINTS]:
    if _mark_cacheable(wire_messages[idx]):
      placed += 1
  return placed


def _usage_numbers(usage: Any) -> tuple[int | None, int | None, int | None]:
  """(prompt_tokens, completion_tokens, cached_tokens) from a LiteLLM usage object or dict."""
  if not usage:
    return None, None, None

  def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

  cached = None
  details = _get(usage, "prompt_tokens_details")
  if details:
    cached = _get(details, "cached_tokens")
  if not cached:
    cached = _get(usage, "cache_read_input_tokens")
  return _get(usage, "prompt_tokens"), _get(usage, "completion_tokens"), cached or 0


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
    fallback_models: list[str] | None = None,
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
    # User-configured fallbacks win over the registry defaults; never retry the primary model.
    chosen = fallback_models if fallback_models is not None else self.spec.fallback_models
    self.fallback_models: list[str] = [m for m in dict.fromkeys(chosen or []) if m and m != self.default_model]

  def _format_model_name(self, model: str) -> str:
    m = model.strip()
    prefix = self.spec.litellm_prefix

    # Special handling for Ollama
    if self.spec.id in {"ollama", "local"} or prefix == "ollama_chat":
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

  def _build_kwargs(
    self,
    messages: list[AIMessage],
    model: str | None = None,
    max_tokens: int | None = None,
    stream: bool = False,
    fallbacks: list[str] | None = None,
    native_fallbacks: bool = True,
    **extra: Any,
  ) -> dict[str, Any]:
    chosen_raw = model or self.default_model
    formatted_model = self._format_model_name(chosen_raw)

    timeout_val = float(os.getenv("AI_TIMEOUT_S", "120" if stream else "60"))
    num_retries_val = int(os.getenv("AI_NUM_RETRIES", "2"))

    kwargs: dict[str, Any] = {
      "model": formatted_model,
      "messages": [message.to_litellm() for message in messages],
      "timeout": timeout_val,
      "num_retries": num_retries_val,
      **self.spec.extra_kwargs,
    }

    if stream:
      kwargs["stream"] = True

    # Streaming handles fallbacks itself (only before the first chunk), so it disables LiteLLM's.
    effective_fallbacks = (fallbacks if fallbacks is not None else self.fallback_models) if native_fallbacks else []
    effective_fallbacks = [fb for fb in effective_fallbacks if fb != chosen_raw]
    if effective_fallbacks:
      kwargs["fallbacks"] = [self._format_model_name(fb) for fb in effective_fallbacks]

    if not (self.id == "gemini" or formatted_model.startswith("gemini/")):
      if "temperature" not in kwargs and "temperature" not in extra:
        kwargs["temperature"] = 0.2

    effective_max_tokens = resolve_model_max_tokens(
      self.id,
      chosen_raw,
      requested_max=max_tokens,
      is_stream=stream,
    )
    kwargs["max_tokens"] = effective_max_tokens

    if self.api_key:
      kwargs["api_key"] = self.api_key
    if self.base_url:
      kwargs["api_base"] = self.base_url

    kwargs.update(extra)

    if self.spec.id in _EXPLICIT_CACHE_PROVIDERS and self.spec.supports_prompt_cache and _prompt_cache_enabled():
      apply_cache_breakpoints(kwargs["messages"])
    if stream and self.spec.id in _STREAM_USAGE_PROVIDERS and "stream_options" not in kwargs:
      kwargs["stream_options"] = {"include_usage": True}
    return kwargs

  async def complete(
    self,
    messages: list[AIMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    fallbacks: list[str] | None = None,
    **extra: Any,
  ) -> AICompletion:
    chosen_raw = model or self.default_model
    kwargs = self._build_kwargs(
      messages=messages,
      model=chosen_raw,
      max_tokens=max_tokens,
      stream=False,
      fallbacks=fallbacks,
      **extra,
    )

    t0 = time.perf_counter()
    try:
      response = await litellm.acompletion(**kwargs)
    except Exception as err:
      raise _handle_completion_error(err) from err

    duration_ms = (time.perf_counter() - t0) * 1000.0
    raw_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)

    cost_usd = None
    prompt_tokens, completion_tokens, cached_tokens = _usage_numbers(getattr(response, "usage", None))
    try:
      cost_usd = litellm.completion_cost(completion_response=response)
    except Exception:
      pass

    text = ""
    parsed_tool_calls: list[ToolCall] = []
    finish_reason = None
    if hasattr(response, "choices") and response.choices:
      choice = response.choices[0]
      finish_reason = getattr(choice, "finish_reason", None)
      if hasattr(choice, "message"):
        msg = choice.message
        text = getattr(msg, "content", "") or ""
        tcs = getattr(msg, "tool_calls", None) or []
        for tc in tcs:
          tc_id = getattr(tc, "id", "")
          fn = getattr(tc, "function", None)
          fn_name = getattr(fn, "name", "") if fn else getattr(tc, "name", "")
          fn_args = getattr(fn, "arguments", {}) if fn else getattr(tc, "arguments", {})
          if isinstance(fn_args, str):
            try:
              import json
              fn_args = json.loads(fn_args)
            except Exception:
              fn_args = {"raw": fn_args}
          parsed_tool_calls.append(ToolCall(id=tc_id, name=fn_name, arguments=fn_args))

    served_model = getattr(response, "model", None) or chosen_raw
    clean_model_name = served_model.split("/")[-1] if "/" in served_model else served_model
    return AICompletion(
      text=text,
      provider=self.id,
      model=clean_model_name,
      raw=raw_dict,
      tool_calls=parsed_tool_calls,
      finish_reason=finish_reason,
      prompt_tokens=prompt_tokens,
      completion_tokens=completion_tokens,
      cached_tokens=cached_tokens,
      cost_usd=cost_usd,
      duration_ms=round(duration_ms, 2),
    )

  async def complete_stream(
    self,
    messages: list[AIMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    fallbacks: list[str] | None = None,
    usage_sink: dict[str, Any] | None = None,
    **extra: Any,
  ):
    """Stream text deltas. If `usage_sink` is given it is filled, when the stream ends, with
    model, prompt/completion/cached tokens, cost, ttft_ms, duration_ms and fallback_used."""
    chosen_raw = model or self.default_model
    models_to_try = [chosen_raw]
    candidate_fallbacks = fallbacks if fallbacks is not None else self.fallback_models
    if candidate_fallbacks:
      models_to_try.extend([fb for fb in candidate_fallbacks if fb != chosen_raw])

    last_error: Exception | None = None
    stream_started = False

    for attempt_model in models_to_try:
      kwargs = self._build_kwargs(
        messages=messages,
        model=attempt_model,
        max_tokens=max_tokens,
        stream=True,
        native_fallbacks=False,
        **extra,
      )
      t0 = time.perf_counter()
      ttft_ms: float | None = None
      final_usage: Any = None
      try:
        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
          stream_started = True
          chunk_usage = getattr(chunk, "usage", None)
          if chunk_usage:
            final_usage = chunk_usage
          if hasattr(chunk, "choices") and chunk.choices:
            choice = chunk.choices[0]
            if hasattr(choice, "delta") and hasattr(choice.delta, "content"):
              delta_content = choice.delta.content
              if delta_content:
                if ttft_ms is None:
                  ttft_ms = (time.perf_counter() - t0) * 1000.0
                yield delta_content
        if usage_sink is not None:
          prompt_t, completion_t, cached_t = _usage_numbers(final_usage)
          cost = None
          if prompt_t is not None:
            try:
              cost = litellm.cost_per_token(
                model=kwargs["model"], prompt_tokens=prompt_t or 0, completion_tokens=completion_t or 0
              )
              cost = sum(cost) if isinstance(cost, tuple) else cost
            except Exception:
              cost = None
          usage_sink.update({
            "model": attempt_model,
            "fallback_used": attempt_model != chosen_raw,
            "prompt_tokens": prompt_t,
            "completion_tokens": completion_t,
            "cached_tokens": cached_t,
            "cost_usd": cost,
            "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
            "duration_ms": round((time.perf_counter() - t0) * 1000.0, 2),
          })
        return
      except Exception as err:
        last_error = _handle_completion_error(err)
        if stream_started:
          raise last_error from err
        logger.warning(
          "Streaming with model %s failed before first chunk; trying fallback if available: %s",
          attempt_model,
          err,
        )

    if last_error:
      raise last_error


