"""Cloud speech-to-text clients (Groq / OpenAI Whisper and OpenAI diarization).

Provider and model are resolved once per job from the user's settings. Requests are retried with
backoff only for transient failures (429, 5xx, timeouts, connection errors), honouring `retry-after`.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx

from app.ai.catalog import pick_diarization_model, pick_transcription_model
from app.ai.providers.factory import get_ai_settings
from app.features.transcription import config
from app.features.transcription.errors import TranscriptionJobError, error_from_status, is_transient

logger = logging.getLogger(__name__)

ENDPOINTS = {
  "groq": "https://api.groq.com/openai/v1/audio/transcriptions",
  "openai": "https://api.openai.com/v1/audio/transcriptions",
}
# Last resort only, when the catalog has no segment-capable model for the provider (empty or
# unreachable catalog). The model is otherwise chosen from the catalog, see `pick_transcription_model`.
FALLBACK_MODEL = {"groq": "whisper-large-v3", "openai": "whisper-1"}
# USD per audio minute, used for cost estimates in metrics only.
PRICE_PER_MINUTE = {"groq": 0.00185, "openai": 0.006, "openai-diarize": 0.006}


@dataclass(frozen=True)
class SpeechTarget:
  provider: str
  api_key: str
  model: str
  diarize: bool = False

  @property
  def label(self) -> str:
    name = "Groq" if self.provider == "groq" else "OpenAI"
    kind = "diarización" if self.diarize else "Whisper"
    return f"{name} {kind} ({self.model})"

  def estimate_cost(self, audio_seconds: float) -> float:
    key = "openai-diarize" if self.diarize else self.provider
    return round(audio_seconds / 60.0 * PRICE_PER_MINUTE.get(key, 0.006), 5)


def _keys(cfg: dict[str, Any]) -> dict[str, str]:
  return {
    "groq": cfg.get("transcription_groq_api_key") or cfg.get("groq_api_key") or os.getenv("GROQ_API_KEY", ""),
    "openai": cfg.get("transcription_openai_api_key") or cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY", ""),
  }


def _transcription_model(provider: str, cfg: dict[str, Any]) -> str:
  """The catalog model for the provider; the configured one only when the catalog confirms it."""
  configured_model = (cfg.get("transcription_model") or "").strip()
  model = pick_transcription_model(provider, configured_model) or FALLBACK_MODEL[provider]
  if configured_model and model != configured_model:
    logger.info(
      "Transcription model %r is not a %s catalog model with timestamped segments; using %s",
      configured_model, provider, model,
    )
  return model


def resolve_speech_target(user_id: Optional[str]) -> SpeechTarget:
  """Provider/model for plain transcription, respecting `transcription_provider`."""
  cfg = get_ai_settings(user_id=user_id)
  keys = _keys(cfg)
  configured = (cfg.get("transcription_provider") or "auto").lower()
  order = ["openai", "groq"] if configured == "openai" else ["groq", "openai"]
  for provider in (p for p in order if keys[p]):
    if configured in {"groq", "openai"} and provider != configured:
      logger.warning("Transcription provider %s has no API key; using %s instead", configured, provider)
    return SpeechTarget(provider=provider, api_key=keys[provider], model=_transcription_model(provider, cfg))
  raise TranscriptionJobError("no_credentials")


def _diarization_model(configured: str) -> Optional[str]:
  """The model to diarize with, or None when the catalog knows of no OpenAI diarization model."""
  model, catalog_known = pick_diarization_model("openai", configured)
  if not catalog_known:
    return configured  # empty or unreachable catalog: trust the configured model
  if model is None:
    logger.warning("No OpenAI diarization model in the catalog (configured %r); transcribing without speakers", configured)
  elif model != configured:
    logger.info("Diarization model %r is not in the catalog; using %s", configured, model)
  return model


def resolve_diarization_target(user_id: Optional[str], requested: bool) -> Optional[SpeechTarget]:
  """OpenAI diarization when requested, enabled in settings and an OpenAI key exists."""
  if not requested:
    return None
  cfg = get_ai_settings(user_id=user_id)
  key = _keys(cfg)["openai"]
  if (cfg.get("transcription_diarization") or "auto").lower() == "off" or not key:
    return None
  model = _diarization_model(config.diarize_model())
  return SpeechTarget(provider="openai", api_key=key, model=model, diarize=True) if model else None


def available_providers(user_id: Optional[str]) -> dict[str, bool]:
  keys = _keys(get_ai_settings(user_id=user_id))
  return {"groq": bool(keys["groq"]), "openai": bool(keys["openai"])}


def _retry_after(response: httpx.Response) -> Optional[float]:
  value = response.headers.get("retry-after")
  try:
    return float(value) if value else None
  except ValueError:
    return None


def _error_detail(response: httpx.Response) -> str:
  try:
    body = response.json()
  except ValueError:
    return response.text[:500]
  err = body.get("error") if isinstance(body, dict) else None
  if isinstance(err, dict):
    return str(err.get("message") or response.text)
  return str(err) if err else response.text[:500]


class SpeechClient:
  """One HTTP client per job; `retries` counts every retry performed (for metrics)."""

  def __init__(self, target: SpeechTarget) -> None:
    self.target = target
    self.retries = 0
    self._client = httpx.AsyncClient(timeout=httpx.Timeout(config.request_timeout_s(), connect=20.0))

  async def aclose(self) -> None:
    await self._client.aclose()

  async def __aenter__(self) -> "SpeechClient":
    return self

  async def __aexit__(self, *exc: object) -> None:
    await self.aclose()

  async def _send(self, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """One request; a non-200 reply becomes a typed error."""
    mime = "audio/mpeg" if path.suffix == ".mp3" else "application/octet-stream"
    with path.open("rb") as fh:
      response = await self._client.post(
        ENDPOINTS[self.target.provider],
        headers={"Authorization": f"Bearer {self.target.api_key}"},
        data=data,
        files={"file": (path.name, fh, mime)},
      )
    if response.status_code == 200:
      return response.json()
    raise error_from_status(response.status_code, _error_detail(response), _retry_after(response))

  async def _post(self, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    attempts = config.num_retries() + 1
    for attempt in range(attempts - 1):
      try:
        return await self._send(path, data)
      except (TranscriptionJobError, httpx.HTTPError) as exc:
        if not is_transient(exc):
          raise
        self.retries += 1
        delay = _backoff_delay(exc, attempt)
        logger.warning("Transient %s error (%s); retry %d/%d in %.1fs", self.target.provider, exc, attempt + 1, attempts - 1, delay)
        await asyncio.sleep(delay)
    return await self._send(path, data)

  async def transcribe(self, path: Path, *, language: Optional[str], prompt: str = "") -> dict[str, Any]:
    """Whisper `verbose_json`: segments carry no_speech_prob / avg_logprob / compression_ratio."""
    data: dict[str, Any] = {"model": self.target.model, "response_format": "verbose_json", "temperature": "0"}
    if language:
      data["language"] = language
    if prompt:
      data["prompt"] = prompt
    body = await self._post(path, data)
    segments = _segments(body, _whisper_segment)
    if not segments and (body.get("text") or "").strip():
      segments.append({"start": 0.0, "end": float(body.get("duration") or 0.0), "text_raw": body["text"].strip(), "_metrics": {}})
    return _result(body, language, segments)

  async def diarize(
    self,
    path: Path,
    *,
    language: Optional[str],
    known_speakers: Sequence[tuple[str, Path]] = (),
  ) -> dict[str, Any]:
    """OpenAI `diarized_json`. `known_speakers` = [(label, clip path)] keeps labels across chunks."""
    data: dict[str, Any] = {
      "model": self.target.model,
      "response_format": "diarized_json",
      "chunking_strategy": "auto",
    }
    if language:
      data["language"] = language
    if known_speakers:
      data["known_speaker_names[]"] = [name for name, _ in known_speakers]
      data["known_speaker_references[]"] = [_data_url(clip) for _, clip in known_speakers]
    body = await self._post(path, data)
    return _result(body, language, _segments(body, _speaker_segment))


def _backoff_delay(exc: BaseException, attempt: int) -> float:
  """The provider's `retry-after` when it gave one, else exponential backoff with jitter; at most a minute."""
  retry_after = getattr(exc, "retry_after", None)
  return min(60.0, retry_after or (2 ** attempt) * 2 + random.uniform(0, 1))


def _timed_segment(seg: dict[str, Any], text: str) -> dict[str, Any]:
  return {"start": float(seg.get("start", 0.0)), "end": float(seg.get("end", 0.0)), "text_raw": text}


def _whisper_segment(seg: dict[str, Any], text: str) -> dict[str, Any]:
  metrics = {key: seg.get(key) for key in ("no_speech_prob", "avg_logprob", "compression_ratio")}
  return {**_timed_segment(seg, text), "_metrics": metrics}


def _speaker_segment(seg: dict[str, Any], text: str) -> dict[str, Any]:
  return {**_timed_segment(seg, text), "speaker_label": str(seg.get("speaker") or "A"), "_metrics": {}}


def _segments(body: dict[str, Any], build) -> list[dict[str, Any]]:
  """The response's segments that carry text, shaped by `build(segment, stripped_text)`."""
  texts = [(seg, (seg.get("text") or "").strip()) for seg in body.get("segments") or []]
  return [build(seg, text) for seg, text in texts if text]


def _result(body: dict[str, Any], language: Optional[str], segments: list[dict[str, Any]]) -> dict[str, Any]:
  return {"language": body.get("language") or language, "segments": segments, "text": body.get("text") or ""}


def _data_url(path: Path) -> str:
  mime = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
  return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


async def transcribe_short_audio(path: Path, user_id: Optional[str], language: Optional[str] = "es") -> str:
  """Voice dictation: one request, no chunking. Raises TranscriptionJobError."""
  target = resolve_speech_target(user_id)
  async with SpeechClient(target) as client:
    result = await client.transcribe(path, language=language)
  return " ".join(s["text_raw"] for s in result["segments"]).strip()
