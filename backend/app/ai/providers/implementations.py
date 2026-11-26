"""Unified LiteLLM provider implementation backed by ProviderSpec registry."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
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
# LiteLLM retries every exception, including permanent ones (model not found, bad key).
# Retries are done by `_with_retries`, which only retries transient errors.
_NO_LITELLM_RETRIES = {"num_retries": 0}
_RETRY_BACKOFF_S = 0.5
_RETRY_BACKOFF_MAX_S = 8.0


_NON_RETRYABLE_CODES = frozenset(
  {"model_not_found", "auth_error", "bad_request", "context_window_exceeded", "max_tokens_exceeded"}
)


def _status_code(err: BaseException) -> int | None:
  code = getattr(err, "status_code", None)
  if code is None:
    response = getattr(err, "response", None)
    code = getattr(response, "status_code", None)
  try:
    return int(code) if code is not None else None
  except (TypeError, ValueError):
    return None


def _is_retryable_status(status: int) -> bool:
  return status in (408, 429) or status >= 500


def is_retryable_error(err: BaseException) -> bool:
  """Whether a provider error is transient. AIError wrappers are judged by their original error."""
  if isinstance(err, AIError):
    if err.code in _NON_RETRYABLE_CODES:
      return False
    err = err.original_error or err
  if isinstance(err, _PERMANENT_ERRORS):
    return False
  if isinstance(err, _TRANSIENT_ERRORS):
    return True
  status = _status_code(err)
  if status is not None:
    return _is_retryable_status(status)
  return isinstance(err, (TimeoutError, ConnectionError))


def is_model_not_found(err: BaseException) -> bool:
  if isinstance(err, AIError):
    return err.code == "model_not_found"
  return isinstance(err, _litellm_types("NotFoundError")) or _status_code(err) == 404


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


def _of_type_or_status(type_names: tuple[str, ...], statuses: tuple[int, ...]):
  """Predicate: the error is one of the named LiteLLM exception types or carries one of the statuses."""
  def matches(err: BaseException, status: int | None) -> bool:
    return isinstance(err, _litellm_types(*type_names)) or status in statuses
  return matches


def _is_timeout(err: BaseException, status: int | None) -> bool:
  return _of_type_or_status(("Timeout",), (408,))(err, status) or isinstance(err, TimeoutError)


def _is_provider_unavailable(err: BaseException, status: int | None) -> bool:
  by_type = isinstance(err, _litellm_types("InternalServerError", "ServiceUnavailableError", "APIConnectionError"))
  return by_type or (status is not None and status >= 500)


def _simple_error(code: str, message: str):
  """Builder of an AIError with a fixed user message."""
  return lambda err: AIError(code=code, user_message=message, original_error=err)


def _number_after(label: str, text: str) -> str | None:
  """The digits following `label` in a provider message, e.g. "Limit 6000"."""
  match = re.search(rf"{label}\s+(\d+)", text, re.IGNORECASE)
  return match.group(1) if match else None


def _quota_numbers(err_str: str) -> tuple[str, str] | None:
  """(limit, requested) token counts quoted in a provider message, when both are present."""
  limit = _number_after("Limit", err_str)
  requested = _number_after("Requested", err_str)
  return (limit, requested) if limit and requested else None


def _otpm_message(wait: str, quota: tuple[str, str] | None) -> str:
  if quota:
    limit, requested = quota
    return (
      f"Límite de tokens de salida por minuto (OTPM) alcanzado ({requested} solicitados, límite {limit}). "
      f"Espera {wait} o selecciona un modelo con mayor cuota en Configuración."
    )
  return f"Límite de tokens de salida por minuto (OTPM) alcanzado. Espera {wait} o selecciona otro modelo."


def _itpm_message(quota: tuple[str, str] | None) -> str:
  if quota:
    limit, requested = quota
    return f"El texto enviado ({requested} tokens) supera el límite de {limit} tokens de entrada por minuto (ITPM)."
  return "El texto enviado supera el límite de tokens de entrada por minuto (ITPM) de este modelo."


def _rpm_message(wait: str, quota: tuple[str, str] | None) -> str:
  if quota:
    limit, requested = quota
    return f"Límite de tasa de tokens por minuto (TPM) alcanzado ({requested} solicitados, límite {limit}). Espera {wait}."
  return f"Límite de peticiones por minuto alcanzado para este modelo. Por favor espera {wait} o selecciona otro modelo."


def _rate_limit_error(err: BaseException) -> AIError:
  """Rate-limit AIError whose message says which limit was hit and how long to wait, when known."""
  err_str = str(err)
  lower = err_str.lower()
  wait_match = re.search(r"try again in ([0-9.]+s?)", err_str, re.IGNORECASE)
  wait = wait_match.group(1) if wait_match else "unos segundos"
  retry_after = float(wait_match.group(1).rstrip("s")) if wait_match else None
  quota = _quota_numbers(err_str)
  if "otpm" in lower or "output tokens per minute" in lower:
    message = _otpm_message(wait, quota)
  elif "itpm" in lower or "input tokens per minute" in lower:
    message = _itpm_message(quota)
  else:
    message = _rpm_message(wait, quota)
  return AIError(code="rate_limit", user_message=message, retry_after=retry_after, original_error=err)


def _bad_request_error(err: BaseException) -> AIError:
  err_str = str(err)
  if "reduce max_tokens" not in err_str.lower():
    return AIError(code="bad_request", user_message=f"Petición inválida al modelo: {err_str}", original_error=err)
  req_tokens = _number_after("Requested", err_str) or "solicitada"
  limit_tokens = _number_after("Limit", err_str) or "establecido"
  return AIError(
    code="max_tokens_exceeded",
    user_message=f"La solicitud con {req_tokens} tokens supera el límite de {limit_tokens} tokens de salida. Te sugerimos seleccionar otro modelo.",
    original_error=err,
  )


# Checked in order; the first predicate that matches decides the AIError. Classification uses the
# exception type and HTTP status code; the message text is only parsed for details, never to decide.
_ERROR_RULES = (
  (
    _of_type_or_status(("ContextWindowExceededError",), (413,)),
    _simple_error(
      "context_window_exceeded",
      "La longitud del texto supera la ventana de contexto del modelo. Te sugerimos seleccionar un modelo con ventana extendida.",
    ),
  ),
  (
    lambda err, status: is_model_not_found(err),
    _simple_error(
      "model_not_found",
      "El modelo configurado no existe o tu cuenta no tiene acceso a él. Selecciona otro modelo en Configuración.",
    ),
  ),
  (_of_type_or_status(("RateLimitError",), (429,)), _rate_limit_error),
  (
    _is_timeout,
    _simple_error("timeout", "La llamada al modelo excedió el tiempo límite de espera. Inténtalo de nuevo."),
  ),
  (
    _of_type_or_status(("AuthenticationError", "PermissionDeniedError"), (401, 403)),
    _simple_error(
      "auth_error", "Error de autenticación con el proveedor del modelo. Verifica tu API Key en Configuración."
    ),
  ),
  (_of_type_or_status(("BadRequestError", "UnprocessableEntityError"), (400, 422)), _bad_request_error),
  (
    _is_provider_unavailable,
    _simple_error(
      "provider_unavailable",
      "El proveedor del modelo no está disponible en este momento. Inténtalo de nuevo en unos minutos.",
    ),
  ),
)


def _handle_completion_error(err: Exception) -> Exception:
  """Translate a provider exception into a typed AIError; unknown errors are returned unchanged."""
  if isinstance(err, AIError):
    return err
  status = _status_code(err)
  for matches, build in _ERROR_RULES:
    if matches(err, status):
      return build(err)
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


def _breakpoint_targets(wire_messages: list[dict[str, Any]]) -> list[int]:
  """Indexes of the last system message and, before a trailing user turn, the end of the history."""
  targets = [i for i, m in enumerate(wire_messages) if m.get("role") == "system"][-1:]
  prev = len(wire_messages) - 2
  if len(wire_messages) >= 3 and wire_messages[-1].get("role") == "user":
    if prev not in targets and wire_messages[prev].get("role") in ("user", "assistant"):
      targets.append(prev)
  return targets


def apply_cache_breakpoints(wire_messages: list[dict[str, Any]]) -> int:
  """Place cache breakpoints on the stable prefix of the conversation.

  Breakpoints: the last system message (system prompt + documentary context) and the last
  message before the current user turn (end of history). Returns how many were placed.
  """
  targets = _breakpoint_targets(wire_messages)[:_MAX_CACHE_BREAKPOINTS]
  return sum(1 for idx in targets if _mark_cacheable(wire_messages[idx]))


def _field(obj: Any, key: str) -> Any:
  return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _usage_numbers(usage: Any) -> tuple[int | None, int | None, int | None]:
  """(prompt_tokens, completion_tokens, cached_tokens) from a LiteLLM usage object or dict."""
  if not usage:
    return None, None, None
  cached = None
  details = _field(usage, "prompt_tokens_details")
  if details:
    cached = _field(details, "cached_tokens")
  if not cached:
    cached = _field(usage, "cache_read_input_tokens")
  return _field(usage, "prompt_tokens"), _field(usage, "completion_tokens"), cached or 0


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


def _merge_function_delta(slot: dict[str, Any], fn: Any) -> None:
  name = _field(fn, "name")
  if isinstance(name, str) and name:
    slot["name"] = name
  args = _field(fn, "arguments")
  if isinstance(args, str):
    slot["arguments"] += args
  elif isinstance(args, dict):
    slot["arguments"] = json.dumps(args, ensure_ascii=False)


def _accumulate_tool_deltas(parts: dict[int, dict[str, Any]], deltas: list[Any]) -> None:
  """Merge streamed tool-call fragments: id and name arrive once, arguments arrive in pieces."""
  for position, tc in enumerate(deltas):
    index = _field(tc, "index")
    slot = parts.setdefault(index if isinstance(index, int) else position, {"id": "", "name": "", "arguments": ""})
    tc_id = _field(tc, "id")
    if isinstance(tc_id, str) and tc_id:
      slot["id"] = tc_id
    fn = _field(tc, "function")
    if fn is not None:
      _merge_function_delta(slot, fn)


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


def _tool_call_from_message(tc: Any) -> ToolCall:
  fn = getattr(tc, "function", None)
  name = getattr(fn, "name", "") if fn else getattr(tc, "name", "")
  arguments = getattr(fn, "arguments", {}) if fn else getattr(tc, "arguments", {})
  return ToolCall(id=getattr(tc, "id", ""), name=name, arguments=_parse_tool_arguments(arguments))


def _parse_first_choice(response: Any) -> tuple[str, list[ToolCall], str | None]:
  """(text, tool calls, finish reason) of the first choice of a completion response."""
  choices = getattr(response, "choices", None)
  if not choices:
    return "", [], None
  choice = choices[0]
  finish_reason = getattr(choice, "finish_reason", None)
  message = getattr(choice, "message", None)
  if message is None:
    return "", [], finish_reason
  tool_calls = [_tool_call_from_message(tc) for tc in getattr(message, "tool_calls", None) or []]
  return getattr(message, "content", "") or "", tool_calls, finish_reason


def _completion_cost(response: Any) -> float | None:
  try:
    return litellm.completion_cost(completion_response=response)
  except Exception:
    return None


def _stream_cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
  """Cost of a finished stream, known only when the provider reported usage."""
  if prompt_tokens is None:
    return None
  try:
    cost = litellm.cost_per_token(
      model=model, prompt_tokens=prompt_tokens or 0, completion_tokens=completion_tokens or 0
    )
    return sum(cost) if isinstance(cost, tuple) else cost
  except Exception:
    return None


@dataclass
class _StreamAttempt:
  """What one streaming attempt has received so far."""

  t0: float = field(default_factory=time.perf_counter)
  ttft_ms: float | None = None
  final_usage: Any = None
  finish_reason: str | None = None
  tool_parts: dict[int, dict[str, Any]] = field(default_factory=dict)
  started: bool = False  # something reached the caller, so a failure can no longer fall back

  def consume(self, chunk: Any) -> str | None:
    """Absorb one chunk; return its text delta, if it has one."""
    usage = getattr(chunk, "usage", None)
    if usage:
      self.final_usage = usage
    choices = getattr(chunk, "choices", None)
    if not choices:
      return None
    choice = choices[0]
    reason = getattr(choice, "finish_reason", None)
    if isinstance(reason, str) and reason:
      self.finish_reason = reason
    delta = getattr(choice, "delta", None)
    return None if delta is None else self._consume_delta(delta)

  def _consume_delta(self, delta: Any) -> str | None:
    """Accumulate the tool-call fragments of a delta and return its text, if any."""
    tool_deltas = getattr(delta, "tool_calls", None)
    if isinstance(tool_deltas, list):
      _accumulate_tool_deltas(self.tool_parts, tool_deltas)
      self.started = True
    content = getattr(delta, "content", None)
    if not (isinstance(content, str) and content):
      return None
    if self.ttft_ms is None:
      self.ttft_ms = (time.perf_counter() - self.t0) * 1000.0
    self.started = True
    return content

  def usage_record(self, wire_model: str, attempt_model: str, chosen_raw: str) -> dict[str, Any]:
    prompt_tokens, completion_tokens, cached_tokens = _usage_numbers(self.final_usage)
    return {
      "model": attempt_model,
      "fallback_used": attempt_model != chosen_raw,
      "prompt_tokens": prompt_tokens,
      "completion_tokens": completion_tokens,
      "cached_tokens": cached_tokens,
      "cost_usd": _stream_cost(wire_model, prompt_tokens, completion_tokens),
      "ttft_ms": round(self.ttft_ms, 2) if self.ttft_ms is not None else None,
      "duration_ms": round((time.perf_counter() - self.t0) * 1000.0, 2),
      "finish_reason": self.finish_reason,
      "tool_calls": _finalize_tool_calls(self.tool_parts),
    }


def _resolve_spec(provider_id: str | ProviderSpec) -> ProviderSpec:
  """The spec itself, the registered spec of that id, or a bare spec for an unregistered provider."""
  if isinstance(provider_id, ProviderSpec):
    return provider_id
  return find_provider_spec(provider_id) or ProviderSpec(
    id=provider_id, name=provider_id.capitalize(), litellm_prefix=provider_id
  )


def _wants_default_temperature(
  provider_id: str, wire_model: str, kwargs: dict[str, Any], extra: dict[str, Any]
) -> bool:
  """Every model but Gemini gets a low default temperature unless the spec or the caller set one."""
  is_gemini = provider_id == "gemini" or wire_model.startswith("gemini/")
  return not is_gemini and "temperature" not in kwargs and "temperature" not in extra


def _ollama_model_name(model: str) -> str:
  return model if model.startswith(("ollama/", "ollama_chat/")) else f"ollama_chat/{model}"


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
    self.spec = _resolve_spec(provider_id)
    self.id = self.spec.id
    self.name = self.spec.name
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
    return self.spec.is_local

  def _retries(self) -> int:
    try:
      return max(0, int(os.getenv("AI_NUM_RETRIES", "2")))
    except ValueError:
      return 2

  def _format_model_name(self, model: str) -> str:
    m = model.strip()
    prefix = self.spec.litellm_prefix
    if self.spec.id in {"ollama", "local"} or prefix == "ollama_chat":
      return _ollama_model_name(m)
    # LiteLLM accepts direct model names for openai.
    if self.spec.id == "openai" or prefix == "":
      return m.removeprefix("openai/")
    if self.spec.id in {"gemini", "google"}:
      return m if m.startswith("gemini/") else f"gemini/{m.removeprefix('models/')}"
    # General rule: do not double the prefix.
    if not prefix or m.startswith(f"{prefix}/"):
      return m
    return f"{prefix}/{m}"

  def _base_kwargs(self, messages: list[AIMessage], wire_model: str, stream: bool) -> dict[str, Any]:
    timeout = float(os.getenv("AI_TIMEOUT_S", "120" if stream else "60"))
    kwargs: dict[str, Any] = {
      "model": wire_model,
      "messages": [message.to_litellm() for message in messages],
      "timeout": timeout,
      **_NO_LITELLM_RETRIES,
      **self.spec.extra_kwargs,
    }
    if stream:
      kwargs["stream"] = True
    return kwargs

  def _apply_policies(self, kwargs: dict[str, Any], stream: bool) -> None:
    """Cloud content policy, prompt-cache breakpoints and streaming usage reporting."""
    # On-premise engines receive the context as is; every other provider (including
    # remote Ollama) gets sanitized, non-confidential content.
    if not self._is_on_premise():
      kwargs["messages"] = enforce_cloud_policy(kwargs["messages"], self.spec.name)
    if self.spec.id in _EXPLICIT_CACHE_PROVIDERS and self.spec.supports_prompt_cache and _prompt_cache_enabled():
      apply_cache_breakpoints(kwargs["messages"])
    if stream and self.spec.id in _STREAM_USAGE_PROVIDERS and "stream_options" not in kwargs:
      kwargs["stream_options"] = {"include_usage": True}

  def _build_kwargs(self, messages: list[AIMessage], model: str | None = None, max_tokens: int | None = None, stream: bool = False, fallbacks: list[str] | None = None, native_fallbacks: bool = True, **extra: Any) -> dict[str, Any]:
    chosen_raw = model or self.default_model
    formatted_model = self._format_model_name(chosen_raw)
    kwargs = self._base_kwargs(messages, formatted_model, stream)

    # Streaming handles fallbacks itself (only before the first chunk), so it disables LiteLLM's.
    candidates = (fallbacks if fallbacks is not None else self.fallback_models) if native_fallbacks else []
    effective_fallbacks = [fb for fb in candidates if fb != chosen_raw]
    if effective_fallbacks:
      kwargs["fallbacks"] = [self._format_model_name(fb) for fb in effective_fallbacks]

    if _wants_default_temperature(self.id, formatted_model, kwargs, extra):
      kwargs["temperature"] = 0.2
    kwargs["max_tokens"] = resolve_model_max_tokens(self.id, chosen_raw, requested_max=max_tokens, is_stream=stream)
    kwargs.update(self._connection_kwargs())
    kwargs.update(extra)
    self._apply_policies(kwargs, stream)
    return kwargs

  def _connection_kwargs(self) -> dict[str, Any]:
    connection = {"api_key": self.api_key, "api_base": self.base_url}
    return {name: value for name, value in connection.items() if value}

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
    kwargs = self._build_kwargs(messages, chosen_raw, max_tokens, fallbacks=fallbacks, **extra)
    t0 = time.perf_counter()
    try:
      response = await _with_retries(
        lambda: litellm.acompletion(**kwargs), retries=self._retries(), label=kwargs["model"],
      )
    except Exception as err:
      raise _handle_completion_error(err) from err
    duration_ms = (time.perf_counter() - t0) * 1000.0

    prompt_tokens, completion_tokens, cached_tokens = _usage_numbers(getattr(response, "usage", None))
    text, tool_calls, finish_reason = _parse_first_choice(response)
    served_model = getattr(response, "model", None) or chosen_raw
    return AICompletion(
      text=text,
      provider=self.id,
      model=served_model.split("/")[-1],
      raw=response.model_dump() if hasattr(response, "model_dump") else dict(response),
      tool_calls=tool_calls,
      finish_reason=finish_reason,
      prompt_tokens=prompt_tokens,
      completion_tokens=completion_tokens,
      cached_tokens=cached_tokens,
      cost_usd=_completion_cost(response),
      duration_ms=round(duration_ms, 2),
    )

  def _models_to_try(self, chosen_raw: str, fallbacks: list[str] | None) -> list[str]:
    candidates = fallbacks if fallbacks is not None else self.fallback_models
    return [chosen_raw, *(fb for fb in candidates or [] if fb != chosen_raw)]

  def _queue_not_found_fallback(
    self, models_to_try: list[str], next_idx: int, error: Exception, requested_model: str | None
  ) -> None:
    """After a missing model, try `not_found_fallback` next, unless the caller chose the model."""
    if (
      requested_model is None
      and self.not_found_fallback
      and is_model_not_found(error)
      and self.not_found_fallback not in models_to_try
    ):
      models_to_try.insert(next_idx, self.not_found_fallback)

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
    models_to_try = self._models_to_try(chosen_raw, fallbacks)
    last_error: Exception | None = None
    idx = 0

    while idx < len(models_to_try):
      attempt_model = models_to_try[idx]
      idx += 1
      kwargs = self._build_kwargs(messages, attempt_model, max_tokens, True, native_fallbacks=False, **extra)
      attempt = _StreamAttempt()
      response: Any = None
      try:
        response = await _with_retries(
          lambda: litellm.acompletion(**kwargs), retries=self._retries(), label=kwargs["model"],
        )
        async for chunk in response:
          delta = attempt.consume(chunk)
          if delta:
            yield delta
        if usage_sink is not None:
          usage_sink.update(attempt.usage_record(kwargs["model"], attempt_model, chosen_raw))
        return
      except Exception as err:
        last_error = _handle_completion_error(err)
        if attempt.started:
          raise last_error from err
        self._queue_not_found_fallback(models_to_try, idx, last_error, model)
        logger.warning(
          "Streaming with model %s failed before first chunk; trying fallback if available: %s",
          attempt_model,
          err,
        )
      finally:
        await _close_stream(response)

    if last_error:
      raise last_error
