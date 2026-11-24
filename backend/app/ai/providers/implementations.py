"""Unified LiteLLM provider implementation backed by ProviderSpec registry."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any
# Disable remote cost map fetch during standard execution
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm

from app.ai.dlp import enforce_cloud_policy
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


def _litellm_types(*names: str) -> tuple[type[BaseException], ...]:
  """Exception classes exported by the installed LiteLLM version (names vary across releases)."""
  found = []
  for name in names:
    cls = getattr(litellm, name, None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
      found.append(cls)
  return tuple(found)


# Errors that will fail again no matter how often they are retried.
_PERMANENT_ERRORS = _litellm_types(
  "NotFoundError",
  "AuthenticationError",
  "PermissionDeniedError",
  "BadRequestError",
  "UnprocessableEntityError",
  "ContextWindowExceededError",
  "ContentPolicyViolationError",
  "BudgetExceededError",
)
# Errors worth retrying with backoff.
_TRANSIENT_ERRORS = _litellm_types(
  "RateLimitError",
  "Timeout",
  "APIConnectionError",
  "InternalServerError",
  "ServiceUnavailableError",
)
_RETRY_BACKOFF_S = 0.5
_RETRY_BACKOFF_MAX_S = 8.0
_PERMANENT_STATUS = frozenset({400, 401, 403, 404, 413, 422})


def _status_code(err: BaseException) -> int | None:
  code = getattr(err, "status_code", None)
  if code is None:
    response = getattr(err, "response", None)
    code = getattr(response, "status_code", None)
  try:
    return int(code) if code is not None else None
  except (TypeError, ValueError):
    return None


def is_retryable_error(err: BaseException) -> bool:
  """Whether a provider error is transient. AIError wrappers are judged by their original error."""
  if isinstance(err, AIError):
    if err.code in {"model_not_found", "auth_error", "bad_request", "context_window_exceeded", "max_tokens_exceeded"}:
      return False
    err = err.original_error or err
  if _PERMANENT_ERRORS and isinstance(err, _PERMANENT_ERRORS):
    return False
  if _TRANSIENT_ERRORS and isinstance(err, _TRANSIENT_ERRORS):
    return True
  status = _status_code(err)
  if status is not None:
    return status not in _PERMANENT_STATUS and (status == 408 or status == 429 or status >= 500)
  return isinstance(err, (TimeoutError, ConnectionError))


def is_model_not_found(err: BaseException) -> bool:
  if isinstance(err, AIError):
    return err.code == "model_not_found"
  not_found = _litellm_types("NotFoundError")
  return (bool(not_found) and isinstance(err, not_found)) or _status_code(err) == 404


async def _with_retries(call, *, retries: int, label: str):
  """Await `call()` retrying only transient errors, with exponential backoff."""
  attempt = 0
  while True:
    try:
      return await call()
    except Exception as err:
      if attempt >= retries or not is_retryable_error(err):
        raise
      delay = min(_RETRY_BACKOFF_MAX_S, _RETRY_BACKOFF_S * (2 ** attempt))
      attempt += 1
      logger.warning("Transient error calling %s (attempt %d/%d), retrying in %.1fs: %s", label, attempt, retries, delay, err)
      if delay > 0:
        await asyncio.sleep(delay)


def _handle_completion_error(err: Exception) -> Exception:
  """Translate a provider exception into a typed AIError.

  Classification uses the exception type and HTTP status code; the message text is only parsed
  for details (limits, wait time), never to decide the category.
  """
  if isinstance(err, AIError):
    return err
  err_str = str(err)
  lower_err = err_str.lower()
  status = _status_code(err)

  context_types = _litellm_types("ContextWindowExceededError")
  if (context_types and isinstance(err, context_types)) or status == 413:
    return AIError(
      code="context_window_exceeded",
      user_message="La longitud del texto supera la ventana de contexto del modelo. Te sugerimos seleccionar un modelo con ventana extendida.",
      original_error=err,
    )

  if is_model_not_found(err):
    return AIError(
      code="model_not_found",
      user_message="El modelo configurado no existe o tu cuenta no tiene acceso a él. Selecciona otro modelo en Configuración.",
      original_error=err,
    )

  rate_types = _litellm_types("RateLimitError")
  if (rate_types and isinstance(err, rate_types)) or status == 429:
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

  timeout_types = _litellm_types("Timeout")
  if (timeout_types and isinstance(err, timeout_types)) or isinstance(err, TimeoutError) or status == 408:
    return AIError(
      code="timeout",
      user_message="La llamada al modelo excedió el tiempo límite de espera. Inténtalo de nuevo.",
      original_error=err,
    )

  auth_types = _litellm_types("AuthenticationError", "PermissionDeniedError")
  if (auth_types and isinstance(err, auth_types)) or status in (401, 403):
    return AIError(
      code="auth_error",
      user_message="Error de autenticación con el proveedor del modelo. Verifica tu API Key en Configuración.",
      original_error=err,
    )

  bad_request_types = _litellm_types("BadRequestError", "UnprocessableEntityError")
  if (bad_request_types and isinstance(err, bad_request_types)) or status in (400, 422):
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

  unavailable_types = _litellm_types("InternalServerError", "ServiceUnavailableError", "APIConnectionError")
  if (unavailable_types and isinstance(err, unavailable_types)) or (status is not None and status >= 500):
    return AIError(
      code="provider_unavailable",
      user_message="El proveedor del modelo no está disponible en este momento. Inténtalo de nuevo en unos minutos.",
      original_error=err,
    )

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
    not_found_fallback: str | None = None,
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
    # Model retried once when the default model no longer exists (fast tier → main model).
    self.not_found_fallback = not_found_fallback if not_found_fallback != self.default_model else None

  def supports_tools(self, model: str | None = None) -> bool:
    """Whether the model can take part in the tool-calling agent loop.

    Asks LiteLLM's model metadata; unknown models count as unsupported so the plain route is used.
    """
    if not self.spec.supports_tools:
      return False
    formatted = self._format_model_name(model or self.default_model)
    try:
      return bool(litellm.supports_function_calling(model=formatted))
    except Exception as exc:
      logger.info("Tool calling support unknown for %s (%s); using the plain route", formatted, exc)
      return False

  def _is_on_premise(self) -> bool:
    return self.spec.is_local or self.spec.id in {"ollama", "local", "ollama_remote"} or "ollama" in self.spec.aliases

  def _retries(self) -> int:
    try:
      return max(0, int(os.getenv("AI_NUM_RETRIES", "2")))
    except ValueError:
      return 2

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

    kwargs: dict[str, Any] = {
      "model": formatted_model,
      "messages": [message.to_litellm() for message in messages],
      "timeout": timeout_val,
      # LiteLLM retries every exception, including permanent ones (model not found, bad key).
      # Retries are done by `_with_retries`, which only retries transient errors.
      "num_retries": 0,
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

    # PRI-06: on-premise engines (Ollama) receive the context as is; cloud providers only get
    # sanitized, non-confidential content.
    if not self._is_on_premise():
      kwargs["messages"] = enforce_cloud_policy(kwargs["messages"], self.spec.name)

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
    try:
      return await self._complete_once(messages, chosen_raw, max_tokens, fallbacks, extra)
    except AIError as err:
      if model is None and self.not_found_fallback and err.code == "model_not_found":
        logger.warning(
          "Model %s/%s not found; retrying once with %s", self.id, chosen_raw, self.not_found_fallback,
        )
        return await self._complete_once(messages, self.not_found_fallback, max_tokens, fallbacks, extra)
      raise

  async def _complete_once(
    self,
    messages: list[AIMessage],
    chosen_raw: str,
    max_tokens: int | None,
    fallbacks: list[str] | None,
    extra: dict[str, Any],
  ) -> AICompletion:
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
      response = await _with_retries(
        lambda: litellm.acompletion(**kwargs), retries=self._retries(), label=kwargs["model"],
      )
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
          parsed_tool_calls.append(ToolCall(id=tc_id, name=fn_name, arguments=_parse_tool_arguments(fn_args)))

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
    """Stream text deltas.

    If `usage_sink` is given it is filled, when the stream ends, with model, prompt/completion/cached
    tokens, cost, ttft_ms, duration_ms, fallback_used, finish_reason and tool_calls (accumulated from
    the streamed tool-call deltas, as `ToolCall` objects).

    Before the first delta is yielded, transient errors are retried and then the fallback models are
    tried in order; a missing model also falls back to `not_found_fallback`. After the first delta,
    errors propagate.
    """
    chosen_raw = model or self.default_model
    models_to_try = [chosen_raw]
    candidate_fallbacks = fallbacks if fallbacks is not None else self.fallback_models
    if candidate_fallbacks:
      models_to_try.extend([fb for fb in candidate_fallbacks if fb != chosen_raw])

    last_error: Exception | None = None
    stream_started = False
    idx = 0

    while idx < len(models_to_try):
      attempt_model = models_to_try[idx]
      idx += 1
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
      finish_reason: str | None = None
      tool_parts: dict[int, dict[str, Any]] = {}
      response: Any = None
      try:
        response = await _with_retries(
          lambda: litellm.acompletion(**kwargs), retries=self._retries(), label=kwargs["model"],
        )
        async for chunk in response:
          chunk_usage = getattr(chunk, "usage", None)
          if chunk_usage:
            final_usage = chunk_usage
          choices = getattr(chunk, "choices", None)
          if not choices:
            continue
          choice = choices[0]
          reason = getattr(choice, "finish_reason", None)
          if isinstance(reason, str) and reason:
            finish_reason = reason
          delta = getattr(choice, "delta", None)
          if delta is None:
            continue
          tool_deltas = getattr(delta, "tool_calls", None)
          if isinstance(tool_deltas, list):
            _accumulate_tool_deltas(tool_parts, tool_deltas)
            stream_started = True
          delta_content = getattr(delta, "content", None)
          if isinstance(delta_content, str) and delta_content:
            if ttft_ms is None:
              ttft_ms = (time.perf_counter() - t0) * 1000.0
            stream_started = True
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
            "finish_reason": finish_reason,
            "tool_calls": _finalize_tool_calls(tool_parts),
          })
        return
      except Exception as err:
        last_error = _handle_completion_error(err)
        if stream_started:
          raise last_error from err
        if (
          model is None
          and self.not_found_fallback
          and is_model_not_found(last_error)
          and self.not_found_fallback not in models_to_try
        ):
          models_to_try.insert(idx, self.not_found_fallback)
        logger.warning(
          "Streaming with model %s failed before first chunk; trying fallback if available: %s",
          attempt_model,
          err,
        )
      finally:
        await _close_stream(response)

    if last_error:
      raise last_error


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
  if isinstance(raw, dict):
    return raw
  if isinstance(raw, str):
    if not raw.strip():
      return {}
    try:
      parsed = json.loads(raw)
      return parsed if isinstance(parsed, dict) else {"value": parsed}
    except ValueError:
      return {"raw": raw}
  return {}


def _field(obj: Any, key: str) -> Any:
  return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _accumulate_tool_deltas(parts: dict[int, dict[str, Any]], deltas: list[Any]) -> None:
  """Merge streamed tool-call fragments: id and name arrive once, arguments arrive in pieces."""
  for position, tc in enumerate(deltas):
    index = _field(tc, "index")
    if not isinstance(index, int):
      index = position
    slot = parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
    tc_id = _field(tc, "id")
    if isinstance(tc_id, str) and tc_id:
      slot["id"] = tc_id
    fn = _field(tc, "function")
    if fn is not None:
      name = _field(fn, "name")
      if isinstance(name, str) and name:
        slot["name"] = name
      args = _field(fn, "arguments")
      if isinstance(args, str):
        slot["arguments"] += args
      elif isinstance(args, dict):
        slot["arguments"] = json.dumps(args, ensure_ascii=False)


def _finalize_tool_calls(parts: dict[int, dict[str, Any]]) -> list[ToolCall]:
  calls: list[ToolCall] = []
  for index in sorted(parts):
    slot = parts[index]
    if not slot["name"]:
      continue
    calls.append(ToolCall(
      id=slot["id"] or f"call_{index}",
      name=slot["name"],
      arguments=_parse_tool_arguments(slot["arguments"]),
    ))
  return calls


async def _close_stream(response: Any) -> None:
  """Release the provider connection when a stream ends early (cancellation, client disconnect)."""
  if response is None:
    return
  for target in (response, getattr(response, "completion_stream", None)):
    closer = getattr(target, "aclose", None)
    if closer is None or not callable(closer):
      continue
    try:
      result = closer()
      if asyncio.iscoroutine(result):
        await result
    except Exception as exc:  # closing is best-effort
      logger.debug("Could not close provider stream: %s", exc)
    return
