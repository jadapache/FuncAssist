"""Typed failures of a transcription job (`error_code` in the progress contract)."""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from app.core.exceptions import AudioAnalysisError, FFmpegError

# code -> (default user message, retryable)
ERROR_CODES: dict[str, tuple[str, bool]] = {
  "file_too_large": ("El archivo supera el tamaño máximo permitido.", False),
  "too_long": ("La grabación supera la duración máxima permitida.", False),
  "unsupported_format": ("El formato del archivo no está soportado.", False),
  "corrupt_media": ("No se pudo leer el audio del archivo. Puede estar dañado.", False),
  "no_credentials": (
    "La transcripción en servidor requiere una clave de API de Groq u OpenAI. "
    "Configúrala en Ajustes o usa la transcripción en el navegador.",
    False,
  ),
  "auth_error": ("La clave de API del proveedor de transcripción no es válida.", False),
  "rate_limit": ("El proveedor de transcripción alcanzó su límite de uso. Inténtalo de nuevo en unos minutos.", True),
  "timeout": ("El proveedor de transcripción tardó demasiado en responder.", True),
  "provider_unavailable": ("El proveedor de transcripción no está disponible en este momento.", True),
  "bad_request": ("El proveedor de transcripción rechazó la petición.", False),
  "empty_result": ("No se detectó voz en la grabación.", False),
  "cancelled": ("Transcripción cancelada por el usuario.", False),
  "interrupted": ("La transcripción se interrumpió por un reinicio del servidor. Puedes reintentarla.", True),
  "internal": ("Error interno durante la transcripción.", True),
}


class TranscriptionJobError(Exception):
  """A job failure with a contract error code, a user-facing message and a retry hint."""

  def __init__(
    self,
    code: str,
    message: Optional[str] = None,
    *,
    detail: str = "",
    retryable: Optional[bool] = None,
    retry_after: Optional[float] = None,
  ) -> None:
    default_message, default_retryable = ERROR_CODES.get(code, ERROR_CODES["internal"])
    self.code = code if code in ERROR_CODES else "internal"
    self.user_message = message or default_message
    self.detail = detail
    self.retryable = default_retryable if retryable is None else retryable
    self.retry_after = retry_after
    super().__init__(f"{self.code}: {detail or self.user_message}")


_STATUS_CODES = {
  400: "bad_request",
  401: "auth_error",
  403: "auth_error",
  404: "bad_request",
  413: "file_too_large",
  415: "unsupported_format",
  422: "bad_request",
  429: "rate_limit",
}


def error_from_status(status: int, detail: str, retry_after: Optional[float] = None) -> TranscriptionJobError:
  if status >= 500:
    return TranscriptionJobError("provider_unavailable", detail=detail, retry_after=retry_after)
  code = _STATUS_CODES.get(status, "bad_request")
  if code == "bad_request" and "api key" in detail.lower():
    code = "auth_error"
  return TranscriptionJobError(code, detail=detail, retry_after=retry_after)


def classify_exception(exc: BaseException) -> TranscriptionJobError:
  """Map any exception raised inside the pipeline to a typed job error."""
  if isinstance(exc, TranscriptionJobError):
    return exc
  if isinstance(exc, asyncio.CancelledError):
    return TranscriptionJobError("cancelled")
  if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)):
    return TranscriptionJobError("timeout", detail=str(exc))
  if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError)):
    return TranscriptionJobError("provider_unavailable", detail=str(exc))
  if isinstance(exc, (AudioAnalysisError, FFmpegError)):
    detail = getattr(exc, "detail", "") or str(exc)
    return TranscriptionJobError("corrupt_media", detail=str(detail))
  if isinstance(exc, FileNotFoundError):
    return TranscriptionJobError("corrupt_media", "El archivo de la transcripción ya no existe en el servidor.", detail=str(exc))
  return TranscriptionJobError("internal", detail=f"{type(exc).__name__}: {exc}")


def is_transient(exc: BaseException) -> bool:
  return classify_exception(exc).code in {"rate_limit", "timeout", "provider_unavailable"}
